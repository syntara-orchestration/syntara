"""Audit outbox data seeder for integration tests.

Generates realistic ``AuditOutboxRecord`` rows with varied payload sizes
and event sources.  Inserts are done via raw SQL for maximum throughput
(bypasses ORM overhead that would skew write-path benchmarks).

The drain worker on the live deployment **will consume** seeded records.
This is intentional for drain/burst tests.  For tests that need records to
persist (e.g., EXPLAIN ANALYZE profiling), the drain worker should be
paused or the test must insert and query within the same transaction.
"""

from __future__ import annotations

import json
import os
import random
import string
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

from syntara.core.models.principal import PrincipalType
from tests.integration.audit.conftest import INSERT_OUTBOX_RECORD_SQL

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

# Event source distribution: 60% CRUD, 40% business (matches production patterns)
_CRUD_WEIGHT = 0.6

# Payload size distribution: 70% small (~500B), 30% large (~2-5KB)
_SMALL_PAYLOAD_WEIGHT = 0.7

# Batch insert size to avoid OOM and long-running transactions
DEFAULT_BATCH_SIZE = 1000

# Default number of rows to seed (override via AUDIT_PERF_SEED_ROWS)
DEFAULT_SEED_ROWS = 1000


def _random_string(length: int) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))  # noqa: S311


def _build_small_crud_payload(*, event_action: str | None = None) -> dict[str, object]:
    """~500B CRUD event payload (typical INSERT/UPDATE on a small table)."""
    resource_id = str(uuid4())
    return {
        "event_id": str(uuid4()),
        "event_category": "system_operation",
        "event_severity": "info",
        "event_status": "success",
        "event_action": event_action or random.choice(["create", "update", "delete"]),  # noqa: S311
        "actor_id": str(uuid4()),
        "actor_type": PrincipalType.USER,
        "actor_username": f"user-{_random_string(6)}",
        "source_component": "database.trigger",
        "resource_urn": f"urn:syntara:workflow:{resource_id}",
        "resource_name": f"perf-test-{_random_string(8)}",
        "workflow_id": str(uuid4()),
        "activity_id": None,
        "execution_id": None,
        "event_message": f"CRUD operation on resource {resource_id}",
        "structured_data": {
            "data_type": "crud_audit",
            "resource_data": {
                "id": resource_id,
                "name": f"resource-{_random_string(8)}",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-06-19T12:00:00Z",
            },
        },
    }


def _build_large_business_payload(*, event_action: str | None = None) -> dict[str, object]:
    """~2-5KB business event payload (workflow execution, agent interaction)."""
    resource_id = str(uuid4())
    execution_id = str(uuid4())
    category = random.choice(["workflow_event", "agent_interaction", "llm_interaction"])  # noqa: S311
    return {
        "event_id": str(uuid4()),
        "event_category": category,
        "event_severity": "info",
        "event_status": "success",
        "event_action": event_action or random.choice(["workflow.execute", "agent.invoke", "llm.call"]),  # noqa: S311
        "actor_id": str(uuid4()),
        "actor_type": random.choice(list(PrincipalType)),  # noqa: S311
        "actor_username": f"user-{_random_string(8)}",
        "source_component": random.choice(  # noqa: S311
            ["workflow.engine", "agent.orchestrator", "llm.gateway"]
        ),
        "resource_urn": f"urn:syntara:execution:{resource_id}",
        "resource_name": f"execution-{_random_string(12)}",
        "workflow_id": str(uuid4()),
        "activity_id": f"activity-{_random_string(6)}",
        "execution_id": execution_id,
        "event_message": f"Business operation completed for execution {execution_id}",
        "structured_data": {
            "data_type": "execution_audit",
            "execution_context": {
                "workflow_name": f"workflow-{_random_string(12)}",
                "execution_status": "completed",
                "duration_ms": random.randint(100, 30000),  # noqa: S311
                "steps_completed": random.randint(1, 20),  # noqa: S311
            },
            "input_summary": {
                "parameter_count": random.randint(1, 10),  # noqa: S311
                "payload_bytes": random.randint(100, 5000),  # noqa: S311
                "parameters": {
                    f"param_{i}": _random_string(random.randint(10, 100))  # noqa: S311
                    for i in range(random.randint(3, 8))  # noqa: S311
                },
            },
            "output_summary": {
                "result_type": random.choice(["json", "text", "binary"]),  # noqa: S311
                "result_bytes": random.randint(50, 8000),  # noqa: S311
                "content_preview": _random_string(random.randint(50, 200)),  # noqa: S311
            },
            "resource_data": {
                "id": resource_id,
                "labels": {f"label-{i}": _random_string(10) for i in range(3)},
            },
        },
    }


def _generate_record(event_action: str | None = None) -> tuple[UUID, str, str]:
    """Generate a single (id, event_source, event_payload_json) tuple.

    Args:
        event_action: If provided, override the event_action field in the payload
                     (useful for marking records for filtering/tracking).

    """
    record_id = uuid4()

    if random.random() < _CRUD_WEIGHT:  # noqa: S311
        event_source = "crud_event"
        if random.random() < _SMALL_PAYLOAD_WEIGHT:  # noqa: S311
            payload = _build_small_crud_payload(event_action=event_action)
        else:
            payload = _build_large_business_payload(event_action=event_action)
    else:
        event_source = "business_event"
        if random.random() < _SMALL_PAYLOAD_WEIGHT:  # noqa: S311
            payload = _build_small_crud_payload(event_action=event_action)
        else:
            payload = _build_large_business_payload(event_action=event_action)

    if event_action is not None:
        payload["event_action"] = event_action

    return record_id, event_source, json.dumps(payload)


@dataclass
class SeedResult:
    """Result of a seeding operation."""

    rows_inserted: int = 0
    record_ids: list[UUID] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    rows_per_second: float = 0.0


async def seed_audit_outbox(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    row_count: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    track_ids: bool = True,
    event_action: str | None = None,
) -> SeedResult:
    """Insert realistic AuditOutboxRecords into the live audit_outbox table.

    Args:
        session_factory: Async session factory connected to the AO database.
        row_count: Number of records to insert.  Defaults to
            ``AUDIT_PERF_SEED_ROWS`` env var or ``DEFAULT_SEED_ROWS``.
        batch_size: Records per INSERT statement (controls transaction size).
        track_ids: Whether to track inserted IDs for cleanup.  Disable for
            high-volume seeding where the drain worker will consume records.
        event_action: Optional event_action value to set in all generated records
            (useful for marking/filtering records in drain tests).

    Returns:
        SeedResult with timing and record tracking info.

    Note:
        The live drain worker will consume these records.  For tests that
        need records to persist, pause the drain worker first or use
        ``seed_audit_outbox_in_transaction`` instead.

    """
    if row_count is None:
        row_count = int(os.environ.get("AUDIT_PERF_SEED_ROWS", str(DEFAULT_SEED_ROWS)))

    result = SeedResult()
    start = time.monotonic()

    remaining = row_count
    while remaining > 0:
        current_batch = min(remaining, batch_size)
        records = [_generate_record(event_action=event_action) for _ in range(current_batch)]

        insert_params: list[dict[str, object]] = []
        for record_id, event_source, payload_json in records:
            insert_params.append({"id": record_id, "source": event_source, "payload": payload_json})

            if track_ids:
                result.record_ids.append(record_id)

        async with session_factory() as session:
            await session.execute(INSERT_OUTBOX_RECORD_SQL, insert_params)
            await session.commit()

        result.rows_inserted += current_batch
        remaining -= current_batch

        if result.rows_inserted % 5000 == 0 or remaining == 0:
            logger.info(
                "audit_perf_seed: progress",
                inserted=result.rows_inserted,
                target=row_count,
            )

    result.elapsed_seconds = time.monotonic() - start
    result.rows_per_second = result.rows_inserted / result.elapsed_seconds if result.elapsed_seconds > 0 else 0

    logger.info(
        "audit_perf_seed: complete",
        rows=result.rows_inserted,
        elapsed_s=round(result.elapsed_seconds, 2),
        rows_per_sec=round(result.rows_per_second, 1),
    )

    return result


async def seed_audit_outbox_in_transaction(
    session: AsyncSession,
    *,
    row_count: int = 100,
) -> list[UUID]:
    """Insert records within an existing transaction (caller controls commit).

    Use this when the test needs records to survive drain worker consumption
    (e.g., by holding the transaction open for the duration of the query).

    Returns:
        List of inserted record IDs.

    """
    record_ids: list[UUID] = []

    for _ in range(row_count):
        record_id, event_source, payload_json = _generate_record()
        record_ids.append(record_id)

        await session.execute(
            INSERT_OUTBOX_RECORD_SQL,
            {"id": record_id, "source": event_source, "payload": payload_json},
        )

    return record_ids
