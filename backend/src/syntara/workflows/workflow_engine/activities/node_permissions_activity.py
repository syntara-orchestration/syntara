"""Activities backing node-kind permissions at runtime (ANSTRAT-1750, slice 4).

Workflow code runs in the Temporal sandbox with no database and no settings
cache, so the three things the engine needs at runtime happen in activities:

- :func:`check_node_kind_enabled` — re-read the kill switch as a node starts, so
  a kind disabled after launch fails that node (AD-19);
- :func:`record_node_execute_denied` — one audit event per denied node (AD-15);
- :func:`recompute_denied_nodes` — re-evaluate the denied set when a suspended
  run resumes, and replace the copy stored on the execution row (AD-12).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy.orm import selectinload
from sqlmodel import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.database.session import AsyncSessionLocal
from syntara.workflows.audit.node_execute_denied import NodeExecuteDeniedEvent
from syntara.workflows.models.execution import Execution
from syntara.workflows.node_kind_switch import NODE_KIND_DISABLED_ERROR_CODE, get_disabled_node_kinds
from syntara.workflows.node_launch_checks import compute_denied_nodes, get_node_authz_evaluator
from syntara.workflows.workflow_engine.constants import (
    CHECK_NODE_KIND_ENABLED_ACTIVITY,
    RECOMPUTE_DENIED_NODES_ACTIVITY,
    RECORD_NODE_EXECUTE_DENIED_ACTIVITY,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name=CHECK_NODE_KIND_ENABLED_ACTIVITY)
async def check_node_kind_enabled(kind: str) -> None:
    """Fail the calling node when its kind is disabled right now.

    Launch already refuses definitions containing a disabled kind; this covers
    the window after launch, when an administrator disables a kind while a run
    is in flight.  The node then fails with normal failed-node semantics.

    Args:
        kind: The node's ``NodeType`` value.

    Raises:
        ApplicationError: Non-retryable, if *kind* is currently disabled —
            re-enabling it is an operator action, not something a retry fixes.

    """
    disabled = await get_disabled_node_kinds()
    if kind in disabled:
        logger.warning("Node start refused: node kind is disabled", node_kind=kind)
        msg = f"Node kind '{kind}' is disabled ({NODE_KIND_DISABLED_ERROR_CODE})"
        raise ApplicationError(
            msg,
            {"output": {"status": "failed", "error": {"code": NODE_KIND_DISABLED_ERROR_CODE, "kind": kind}}},
            type="NodeKindDisabledError",
            non_retryable=True,
        )


@activity.defn(name=RECORD_NODE_EXECUTE_DENIED_ACTIVITY)
async def record_node_execute_denied(
    execution_id: str,
    node_id: str,
    kind: str,
    denied_by: str,
    principal_id: str | None = None,
) -> None:
    """Emit the audit event for one node that was not executed because of a denial."""
    async with AsyncSessionLocal() as session:
        result = await session.exec(select(Execution.workflow_id).where(Execution.id == UUID(execution_id)))
        workflow_id = result.first()

    AuditEventDispatcher.dispatch(
        NodeExecuteDeniedEvent(
            execution_id=UUID(execution_id),
            node_id=node_id,
            kind=kind,
            denied_by=denied_by,
            principal_id=UUID(principal_id) if principal_id else None,
            workflow_id=workflow_id,
        )
    )


@activity.defn(name=RECOMPUTE_DENIED_NODES_ACTIVITY)
async def recompute_denied_nodes(execution_id: str, principal_id: str) -> list[dict[str, Any]]:
    """Re-evaluate the denied set for a resuming execution and persist it.

    A run suspended on an approval or a wait can resume hours later; the fresh
    verdict, not the one taken at launch, decides what still runs (AD-12).

    Args:
        execution_id: Execution being resumed.
        principal_id: Principal the run acts with.

    Returns:
        The refreshed ``[{node_id, kind, denied_by}]`` list.

    """
    async with AsyncSessionLocal() as session:
        result = await session.exec(
            select(Execution)
            .where(Execution.id == UUID(execution_id))
            .options(selectinload(Execution.workflow_version))  # type: ignore[arg-type]
        )
        execution = result.one_or_none()
        if execution is None:
            logger.warning("Cannot re-check node denials: execution not found", execution_id=execution_id)
            return []

        denied_nodes = await compute_denied_nodes(
            session,
            get_node_authz_evaluator(),
            definition=execution.workflow_version.workflow_definition,
            project_id=execution.project_id,
            principal_id=UUID(principal_id),
        )
        execution.denied_nodes = denied_nodes or None
        await session.commit()

    logger.info(
        "Re-checked node denials on resume",
        execution_id=execution_id,
        denied_node_ids=[entry["node_id"] for entry in denied_nodes],
    )
    return denied_nodes


NODE_PERMISSION_ACTIVITIES: list[Callable[..., Any]] = [
    check_node_kind_enabled,
    record_node_execute_denied,
    recompute_denied_nodes,
]
"""Activities registered on every worker that runs ``OrchestratorWorkflow``."""
