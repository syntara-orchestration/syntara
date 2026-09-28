"""Authorization gate shared by every workflow launch path."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import structlog
from sqlmodel import select

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.engine import AuthzRequest, authorize
from syntara.core.models import User
from syntara.service_accounts.models.service_account import ServiceAccount, ServiceAccountStatus
from syntara.workflows.audit.launch_rejected import WorkflowLaunchRejectedEvent
from syntara.workflows.node_kinds import NODE_KIND_LABEL, get_node_kind
from syntara.workflows.node_permissions import evaluate_node_labels, resolve_project_name

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.authz.evaluator import AuthzEvaluator

logger = structlog.stdlib.get_logger(__name__)
_evaluator: AuthzEvaluator | None = None

LaunchRejectionReason = Literal["principal_inactive", "execution_run_denied", "step_type_denied"]


@dataclass(frozen=True)
class WorkflowLaunchRejection:
    """The structured reason a launch was rejected."""

    reason: LaunchRejectionReason
    principal_id: UUID
    project_id: UUID
    trigger_type: str | None
    denied_steps: list[dict[str, str]]
    denied_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the stable API and persisted error shape."""
        return {
            "code": "WORKFLOW_LAUNCH_REJECTED",
            "reason": self.reason,
            "principal_id": str(self.principal_id),
            "project_id": str(self.project_id),
            "trigger_type": self.trigger_type,
            "denied_steps": self.denied_steps,
            "denied_by": self.denied_by,
        }


def set_node_authz_evaluator(evaluator: AuthzEvaluator | None) -> None:
    """Register the process evaluator used by scheduler worker launches."""
    global _evaluator  # noqa: PLW0603
    _evaluator = evaluator


def get_node_authz_evaluator() -> AuthzEvaluator | None:
    """Return the evaluator registered by the worker lifecycle."""
    return _evaluator


async def check_workflow_launch(
    db: AsyncSession,
    evaluator: AuthzEvaluator | None,
    *,
    definition: dict[str, Any],
    principal_id: UUID,
    project_id: UUID,
    trigger_type: str | None,
) -> WorkflowLaunchRejection | None:
    """Check an active principal's run permission and each saved action kind once."""
    user_result = await db.exec(select(User).where(User.id == principal_id))
    user = user_result.first()
    if user is not None:
        active = user.is_enabled
        user_labels = dict(user.labels or {})
        user_metadata = dict(user.authz_metadata or {})
    else:
        sa_result = await db.exec(select(ServiceAccount).where(ServiceAccount.id == principal_id))
        service_account = sa_result.first()
        active = service_account is not None and service_account.status == ServiceAccountStatus.ACTIVE
        user_labels = dict(service_account.labels or {}) if service_account else {}
        user_metadata = {}

    if not active:
        return _reject("principal_inactive", principal_id, project_id, trigger_type)

    if evaluator is None:
        # Keep the existing evaluator-outage behavior for authorization checks.
        logger.warning("Authorization evaluator unavailable during workflow launch", principal_id=str(principal_id))
        return None

    project_name = await resolve_project_name(db, project_id)
    run_result = await authorize(
        db,
        evaluator,
        AuthzRequest(
            user_id=principal_id,
            action="run",
            resource_type="execution",
            resource_id="",
            resource_project=project_name,
            user_labels=user_labels,
            user_metadata=user_metadata,
        ),
    )
    if not run_result.allowed:
        return _reject(
            "execution_run_denied",
            principal_id,
            project_id,
            trigger_type,
            denied_by=run_result.denied_by or None,
        )

    kinds_to_nodes: dict[str, list[str]] = {}
    for node in [*(definition.get("triggers") or []), *(definition.get("nodes") or [])]:
        if not isinstance(node, dict):
            continue
        kind, node_id = node.get("type"), node.get("id")
        if isinstance(kind, str) and isinstance(node_id, str) and get_node_kind(kind) is not None:
            kinds_to_nodes.setdefault(kind, []).append(node_id)

    label_sets = {frozenset({(NODE_KIND_LABEL, kind)}) for kind in kinds_to_nodes}
    if not label_sets:
        return None
    results = await evaluate_node_labels(
        db,
        evaluator,
        user_id=principal_id,
        action="execute",
        label_sets=label_sets,
        project_name=project_name,
        user_labels=user_labels,
        user_metadata=user_metadata,
    )
    denied_steps = [
        {
            "node_id": node_id,
            "kind": kind,
            "denied_by": results[frozenset({(NODE_KIND_LABEL, kind)})].denied_by,
        }
        for kind in sorted(kinds_to_nodes)
        if not results[frozenset({(NODE_KIND_LABEL, kind)})].allowed
        for node_id in kinds_to_nodes[kind]
    ]
    if denied_steps:
        return _reject("step_type_denied", principal_id, project_id, trigger_type, denied_steps=denied_steps)
    return None


def _reject(
    reason: LaunchRejectionReason,
    principal_id: UUID,
    project_id: UUID,
    trigger_type: str | None,
    *,
    denied_steps: list[dict[str, str]] | None = None,
    denied_by: str | None = None,
) -> WorkflowLaunchRejection:
    rejection = WorkflowLaunchRejection(
        reason=reason,
        principal_id=principal_id,
        project_id=project_id,
        trigger_type=trigger_type,
        denied_steps=denied_steps or [],
        denied_by=denied_by,
    )
    AuditEventDispatcher.dispatch(WorkflowLaunchRejectedEvent(rejection))
    return rejection


def rejection_error_details(rejection: WorkflowLaunchRejection) -> str:
    """Encode rejection data for the existing Runs error-details field."""
    return json.dumps(rejection.to_dict(), sort_keys=True)
