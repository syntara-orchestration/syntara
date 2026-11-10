"""Step-type write checks shared by workflow writes and project deletion."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.utils import resolve_actor_type
from syntara.authz.audit.authorization_denied import AuthorizationDeniedEvent
from syntara.authz.engine import AuthzRequest, AuthzResult, authorize
from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.authz.models.project import Project
from syntara.core.models import User
from syntara.workflows.exceptions import NodeKindWriteDeniedError
from syntara.workflows.models.node_permission import BlockedStepType
from syntara.workflows.node_kinds import (
    NODE_ACTION_WRITE,
    NODE_RESOURCE_TYPE,
    node_kind_display_label,
    step_types_in_definitions,
)

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True)
class NodeKindDenial:
    """Retain policy provenance for audit, separate from the public response."""

    blocked: BlockedStepType
    policy: str | None = None
    scope: str | None = None


def node_kind_denial(kind: str, project_name: str, result: AuthzResult) -> NodeKindDenial | None:
    """Describe a blocked kind using the exact effective denying statement."""
    if result.allowed:
        return None
    statement = next((p for p in result.effective_policies if p.get("name") == result.denied_by), {})
    explicit = result.denied or bool(result.denied_by)
    scope = statement.get("scope") if explicit else None
    return NodeKindDenial(
        blocked=BlockedStepType(
            kind=kind,
            label=node_kind_display_label(kind),
            reason="explicit_deny" if explicit else "no_matching_allow",
            project=statement.get("project") if explicit else project_name,
        ),
        policy=result.policy_name(result.denied_by) if result.denied_by else None,
        scope=scope,
    )


async def check_node_kind_write_permission(
    db: AsyncSession,
    evaluator: AuthzEvaluator | None,
    user: User,
    definitions: Iterable[dict[str, Any]],
    *,
    project_id: UUID | None,
    operation: str,
    resource_id: str = "",
    resource_name: str = "",
) -> None:
    """Check each distinct type before any write, including unchanged definitions."""
    kinds = step_types_in_definitions(list(definitions))
    project_name = await db.scalar(select(Project.name).where(Project.id == project_id)) if project_id else None
    if not project_name:
        msg = "Cannot verify step-type write permission without a workflow project"
        raise AuthorizationDeniedError(msg)

    def audit_denial(kind: str, reason: str, policy: str | None = None, scope: str | None = None) -> None:
        AuditEventDispatcher.dispatch(
            AuthorizationDeniedEvent(
                user_id=user.id,
                username=user.username,
                principal_type=resolve_actor_type(user.id, principal_type=user.__dict__.get("__principal_type__")),
                resource_type=NODE_RESOURCE_TYPE,
                resource_id=resource_id,
                resource_name=resource_name,
                action=operation,
                denied_by=policy,
                context={"kind": kind, "reason": reason, "scope": scope, "project": project_name},
            )
        )

    if evaluator is None:
        for kind in kinds:
            audit_denial(kind, "evaluation_unavailable")
        msg = "Authorization service unavailable; cannot verify step-type write permission"
        raise AuthorizationDeniedError(msg)

    denials: list[NodeKindDenial] = []
    for kind in kinds:
        try:
            result = await authorize(
                db,
                evaluator,
                AuthzRequest(
                    user_id=user.id,
                    action=NODE_ACTION_WRITE,
                    resource_type=NODE_RESOURCE_TYPE,
                    resource_id="",
                    resource_labels={"kind": kind},
                    resource_project=project_name,
                    user_labels=user.labels,
                    user_metadata=user.authz_metadata,
                ),
            )
        except Exception as exc:
            logger.exception("Step-type authorization evaluation failed", kind=kind, operation=operation)
            audit_denial(kind, "evaluation_unavailable")
            msg = "Authorization service unavailable; cannot verify step-type write permission"
            raise AuthorizationDeniedError(msg) from exc
        denial = node_kind_denial(kind, project_name, result)
        if denial is not None:
            denials.append(denial)
            audit_denial(kind, denial.blocked.reason, denial.policy, denial.scope)
    if denials:
        raise NodeKindWriteDeniedError(operation, [denial.blocked for denial in denials])
