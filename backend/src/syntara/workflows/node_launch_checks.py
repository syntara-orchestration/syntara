"""Launch-time node-kind checks (ANSTRAT-1750).

Two independent gates run just before an execution is handed to Temporal:

- the **kill switch** (design §6b, AD-21): if the definition still contains a
  node whose kind was disabled platform-wide, the launch is refused and nothing
  is started;
- the **execute denial set** (F-15, F-18): every action node whose kind the run
  principal may not execute is recorded, persisted on
  :attr:`~syntara.workflows.models.execution.Execution.denied_nodes` and handed
  to the Temporal workflow as part of its (HMAC-signed) input.  A node denial
  never refuses a launch — the run starts and those nodes end up ``denied``.

The denied set is always evaluated fresh at launch: a policy change between two
fires of the same schedule must take effect on the next fire (F-15).

Evaluator plumbing: the API passes the evaluator it already has on
``app.state``; worker processes have no request to read it from, so they
register theirs at startup with :func:`set_node_authz_evaluator` and activities
pick it up with :func:`get_node_authz_evaluator`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import select

from syntara.core.models import User
from syntara.service_accounts.models.service_account import ServiceAccount
from syntara.workflows.exceptions import NodeKindDisabledError
from syntara.workflows.node_kind_switch import disabled_nodes_in_definition, get_disabled_node_kinds
from syntara.workflows.node_kinds import NODE_ACTION_EXECUTE, node_labels
from syntara.workflows.node_permissions import (
    denied_node_labels,
    executable_label_sets,
    label_sets_in_definition,
    resolve_project_name,
)
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.authz.evaluator import AuthzEvaluator
    from syntara.workflows.models.workflow_version import WorkflowVersion

logger = structlog.stdlib.get_logger(__name__)

PUBLISHER_PRINCIPAL_TRIGGER_TYPES: frozenset[str] = frozenset(
    {NodeType.SCHEDULED_TRIGGER.value, NodeType.WEBHOOK_TRIGGER.value, NodeType.EDA_TRIGGER.value}
)
"""Trigger types whose runs act as the publisher of the version, not as the caller (F-15)."""

_evaluator: AuthzEvaluator | None = None


def set_node_authz_evaluator(evaluator: AuthzEvaluator | None) -> None:
    """Register the process-wide evaluator used by worker-side node checks.

    Called once at worker startup.  Creating a Rego evaluator opens native
    resources, so it must happen at process start, never inside workflow code.
    """
    global _evaluator  # noqa: PLW0603
    _evaluator = evaluator


def get_node_authz_evaluator() -> AuthzEvaluator | None:
    """Return the process-wide evaluator, or ``None`` when none was registered."""
    return _evaluator


async def check_node_kinds_enabled(definition: dict[str, Any] | None) -> None:
    """Refuse a launch whose definition contains a disabled node kind.

    Args:
        definition: Workflow definition about to be executed.

    Raises:
        NodeKindDisabledError: If any node's kind is currently disabled.

    """
    disabled = await get_disabled_node_kinds()
    found = disabled_nodes_in_definition(definition, disabled)
    if found:
        raise NodeKindDisabledError(found)


async def load_principal_authz_context(
    db: AsyncSession,
    principal_id: UUID,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Return ``(labels, authz_metadata)`` for *principal_id*.

    Principals are users or service accounts; both may carry labels, only
    users carry authorization metadata.  An unknown principal (for example the
    schedule service principal, which has no row of its own) yields empty
    context so the evaluation still runs against its roles.
    """
    user_row = await db.exec(select(User).where(User.id == principal_id))
    user = user_row.first()
    if user is not None:
        return dict(user.labels or {}), dict(user.authz_metadata or {})

    sa_row = await db.exec(select(ServiceAccount).where(ServiceAccount.id == principal_id))
    service_account = sa_row.first()
    if service_account is not None:
        return dict(service_account.labels or {}), {}

    return {}, {}


def resolve_run_principal(
    workflow_version: WorkflowVersion,
    *,
    invoker_id: UUID,
    trigger_type: str | None,
) -> UUID:
    """Return the principal whose permissions a run acts with.

    Manual, API and test runs act as the caller.  Triggered runs (scheduled,
    webhook and EDA) have no interactive caller -- a webhook caller merely
    fires the trigger -- so they act as the publisher of the version
    (``published_by``), falling back to the version's author for versions
    published before that column existed.
    """
    if trigger_type in PUBLISHER_PRINCIPAL_TRIGGER_TYPES:
        return workflow_version.published_by or workflow_version.created_by
    return invoker_id


async def compute_denied_nodes(
    db: AsyncSession,
    evaluator: AuthzEvaluator | None,
    *,
    definition: dict[str, Any] | None,
    project_id: UUID | str | None,
    principal_id: UUID,
) -> list[dict[str, Any]]:
    """Return ``[{node_id, kind, denied_by}]`` for every node the principal may not execute.

    Only action kinds are evaluated — triggers and flow control are never
    deniable for ``execute``.  Each distinct kind is evaluated once and the
    verdict is fanned out to every node of that kind, so a definition with
    twenty script nodes costs one evaluation.

    Returns an empty list when no evaluator is available; a missing evaluator
    must never silently deny, and it is logged so the gap is visible.
    """
    label_sets = executable_label_sets(label_sets_in_definition(definition))
    if not label_sets:
        return []

    if evaluator is None:
        logger.warning(
            "No authorization evaluator available — skipping workflow_node:execute checks",
            principal_id=str(principal_id),
        )
        return []

    project_name = await resolve_project_name(db, project_id)
    user_labels, user_metadata = await load_principal_authz_context(db, principal_id)
    denials = await denied_node_labels(
        db,
        evaluator,
        user_id=principal_id,
        action=NODE_ACTION_EXECUTE,
        label_sets=label_sets,
        project_name=project_name,
        user_labels=user_labels,
        user_metadata=user_metadata,
    )
    if not denials:
        return []

    denied_by_labels = {frozenset(denial.labels.items()): denial.denied_by for denial in denials}
    denied_nodes: list[dict[str, Any]] = []
    for node in (definition or {}).get("nodes") or []:
        if not isinstance(node, dict):
            continue
        labels = node_labels(node)
        kind = labels.get("kind")
        node_id = node.get("id")
        label_set = frozenset(labels.items())
        if not isinstance(kind, str) or not isinstance(node_id, str) or label_set not in denied_by_labels:
            continue
        denied_nodes.append(
            {"node_id": node_id, "kind": kind, "labels": labels, "denied_by": denied_by_labels[label_set]}
        )

    if denied_nodes:
        logger.info(
            "Nodes denied for execution",
            principal_id=str(principal_id),
            denied_node_ids=[entry["node_id"] for entry in denied_nodes],
        )
    return denied_nodes
