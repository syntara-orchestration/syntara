"""Periodic reconciliation of Temporal Schedules against published workflows.

Runs a diff-based reconciliation cycle that:

1. Lists all ``orchestrator-sched-*`` Temporal Schedules to build the
   *actual* set.
2. Queries the database for published workflow versions with scheduled
   triggers to build the *expected* set (after the list, so a republish
   that landed during connect/list is not treated as an orphan).
3. Creates missing schedules (from failed publishes) and deletes orphans
   (from unpublish/delete that couldn't reach Temporal).

Steady-state cost: two reads (one Temporal, one DB), zero writes.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, literal_column
from sqlmodel import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession
    from temporalio.client import Client

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers.periodic import PeriodicWorker
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.scheduled_trigger_service import (
    ScheduledTriggerService,
)
from syntara.workflows.utils.schedule_parser import build_schedule_id
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

logger = structlog.stdlib.get_logger(__name__)

# Skip this cycle if Temporal connect, list, or mutate hangs. Waiters shield
# the shared connect; a timed-out get_client returns None to this cycle only
# and leaves the connect running for overlapping publish/delete waiters.
_RECONCILE_TEMPORAL_TIMEOUT_SECONDS = 10.0


def _extract_expected_schedules(
    rows: list[tuple[str, list[dict[str, Any]]]],
) -> dict[str, tuple[str, str, dict[str, Any]]]:
    """Build a lookup of expected schedule IDs from trigger arrays.

    Args:
        rows: List of (workflow_id_str, triggers_array) tuples.

    Returns:
        Dict mapping each schedule ID to (workflow_id, trigger_node_id, config).

    """
    lookup: dict[str, tuple[str, str, dict[str, Any]]] = {}

    for workflow_id_str, triggers in rows:
        for trigger in triggers:
            if trigger.get("type") != NodeType.SCHEDULED_TRIGGER:
                continue
            node_id = trigger.get("id")
            if not node_id:
                continue
            schedule_id = build_schedule_id(workflow_id_str, node_id)
            lookup[schedule_id] = (workflow_id_str, node_id, trigger.get("parameters", {}))

    return lookup


async def _load_expected_schedules(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, tuple[str, str, dict[str, Any]]]:
    """Load expected Temporal schedule IDs from currently published workflows."""
    triggers_col = WorkflowVersion.workflow_definition["triggers"]
    async with session_factory() as session:
        result = await session.exec(
            select(Workflow.id, triggers_col)
            .join(WorkflowVersion, WorkflowVersion.id == Workflow.published_version_id)  # type: ignore[arg-type]
            .where(
                Workflow.published_version_id.is_not(None),  # type: ignore[union-attr]
                Workflow.deleted_at.is_(None),  # type: ignore[union-attr]
                func.jsonb_path_exists(
                    WorkflowVersion.workflow_definition,
                    literal_column("'$.triggers[*] ? (@.type == \"scheduled_trigger\")'::jsonpath"),
                ),
            )
        )
        rows = [(str(wf_id), triggers) for wf_id, triggers in result.all()]
    return _extract_expected_schedules(rows)


async def _fetch_actual_schedules() -> tuple[ScheduledTriggerService, Client, set[str]] | None:
    """Connect and list Temporal schedules, or skip this cycle on timeout."""
    service = ScheduledTriggerService()
    try:
        async with asyncio.timeout(_RECONCILE_TEMPORAL_TIMEOUT_SECONDS):
            client = await service.get_client()
    except TimeoutError:
        logger.warning("schedule_reconciliation_skipped", reason="Temporal client timed out")
        return None

    if client is None:
        logger.warning("schedule_reconciliation_skipped", reason="Temporal unavailable")
        return None

    try:
        async with asyncio.timeout(_RECONCILE_TEMPORAL_TIMEOUT_SECONDS):
            actual_ids = await service.list_all_schedules(client)
    except TimeoutError:
        logger.warning("schedule_reconciliation_skipped", reason="Temporal list timed out")
        return None
    return service, client, actual_ids


async def _apply_schedule_delta(
    service: ScheduledTriggerService,
    client: Client,
    lookup: dict[str, tuple[str, str, dict[str, Any]]],
    missing_list: list[str],
    orphan_list: list[str],
) -> list[object] | None:
    """Create missing schedules and delete orphans, or skip on timeout."""
    try:
        async with asyncio.timeout(_RECONCILE_TEMPORAL_TIMEOUT_SECONDS):
            return list(
                await asyncio.gather(
                    *(service.create_schedule(*lookup[sid]) for sid in missing_list),
                    *(ScheduledTriggerService.delete_schedule(client, sid) for sid in orphan_list),
                    return_exceptions=True,
                )
            )
    except TimeoutError:
        logger.warning("schedule_reconciliation_skipped", reason="Temporal mutate timed out")
        return None


async def reconcile_scheduled_triggers(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    """Diff-based reconciliation of Temporal Schedules against published workflows.

    Called by the PeriodicWorker each cycle.  Resilient to individual
    schedule failures — one broken schedule does not block the rest.
    """
    if session_factory is None:
        return

    fetched = await _fetch_actual_schedules()
    if fetched is None:
        return
    service, client, actual_ids = fetched

    # Load expected *after* list so a republish that landed during
    # connect/list is not deleted as an orphan.
    lookup = await _load_expected_schedules(session_factory)
    expected_ids = set(lookup)
    missing = expected_ids - actual_ids
    orphans = actual_ids - expected_ids

    if not missing and not orphans:
        logger.debug(
            "schedule_reconciliation_noop",
            expected=len(expected_ids),
            actual=len(actual_ids),
        )
        return

    missing_list = sorted(missing)
    orphan_list = sorted(orphans)
    all_results = await _apply_schedule_delta(service, client, lookup, missing_list, orphan_list)
    if all_results is None:
        return
    create_results = all_results[: len(missing_list)]
    delete_results = all_results[len(missing_list) :]

    created = sum(1 for r in create_results if not isinstance(r, Exception))
    for sid, outcome in zip(missing_list, create_results, strict=True):
        if isinstance(outcome, Exception):
            logger.warning("schedule_reconciliation_create_failed", schedule_id=sid, exc_info=outcome)

    deleted = sum(1 for r in delete_results if r is True)
    for sid, outcome in zip(orphan_list, delete_results, strict=True):
        if isinstance(outcome, Exception):
            logger.warning("schedule_reconciliation_delete_failed", schedule_id=sid, exc_info=outcome)

    logger.info(
        "schedule_reconciliation_completed",
        expected=len(expected_ids),
        actual=len(actual_ids),
        created=created,
        deleted=deleted,
        create_errors=len(missing_list) - created,
        delete_errors=len(orphan_list) - deleted,
    )


@lru_cache(maxsize=1)
def get_schedule_reconciliation_worker() -> PeriodicWorker:
    """Create the periodic schedule reconciliation worker."""
    settings = get_settings()
    return PeriodicWorker(
        name="schedule-reconciliation",
        interval_seconds=settings.schedule_reconciliation_interval_seconds,
        session_factory=AsyncSessionLocal,
        callback=reconcile_scheduled_triggers,
        coordinate=True,
    )
