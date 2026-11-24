"""Project-scoped step-type permissions for the add-step panel (ANSTRAT-2533 P6).

One system-scoped endpoint:

- ``GET /node_kinds?project_id=<uuid>`` — every registered step type with its
  category, the caller's own ``step_type:write`` verdict in that project
  (``can_write``) and, when blocked, the policy that blocks it (``blocked_by``,
  the Blocked step type shape agreed in P2).

The UI never sends resource labels through ``can_i`` — it checks one action at
a time — so this endpoint evaluates every step type server-side in a single
request. Evaluation uses the ordinary authorization path (``authorize`` with a
``kind`` resource label and the destination project), so a project deny shows
up only in that project, a global deny in every project, and a missing allow
is reported as ``no_matching_allow``.

The prefix is top-level rather than ``/workflows/node_kinds`` on purpose:
routers are auto-discovered in filesystem order, so a static path nested under
the workflows router could be shadowed by ``/workflows/{workflow_id}``.

The ANSTRAT-1750 prototype's kill-switch write route (``PUT
/{kind}/enabled``) is deliberately not ported: restricting step types is done
with deny policies, not by disabling kinds platform-wide.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.dependencies import get_authz_evaluator
from syntara.authz.engine import AuthzRequest, authorize_resolved
from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.exceptions import ProjectNotFoundError
from syntara.authz.models.project import Project
from syntara.authz.resolver import resolve_effective_policies, resolve_user_groups
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.workflow_core.models import NodeType
from syntara.workflows.node_kinds import (
    NODE_ACTION_WRITE,
    NODE_RESOURCE_TYPE,
    node_kind_display_label,
)

router = SyntaraRouter(prefix="/node_kinds", tags=["Node Kinds"])

#: The action every verdict is evaluated with, as a policy-resolution filter.
ACTION_FILTER = f"{NODE_RESOURCE_TYPE}:{NODE_ACTION_WRITE}"

# Registry grouping reported per kind. Mirrors the builder palette families
# (trigger, logic, action) and the authoring-policy categories from P1.
TRIGGER_KINDS: frozenset[str] = frozenset(
    {
        NodeType.MANUAL_TRIGGER.value,
        NodeType.SCHEDULED_TRIGGER.value,
        NodeType.WEBHOOK_TRIGGER.value,
        NodeType.EDA_TRIGGER.value,
    }
)
FLOW_CONTROL_KINDS: frozenset[str] = frozenset(
    {
        NodeType.CONDITION.value,
        NodeType.CONVERGE.value,
        NodeType.LOOP.value,
        NodeType.SWITCH.value,
        NodeType.WAIT.value,
    }
)
# Every grantable kind in NodeType declaration order (system-only types such as
# internal_activity stay out of the authoring catalog).
_ALL_GRANTABLE_KINDS: tuple[str, ...] = tuple(
    node_type.value for node_type in NodeType if node_type.value != NodeType.INTERNAL_ACTIVITY.value
)


def _category(kind: str) -> str:
    """Return the palette family a step type belongs to."""
    if kind in TRIGGER_KINDS:
        return "trigger"
    if kind in FLOW_CONTROL_KINDS:
        return "flow_control"
    return "action"


# ============================================================================
# Schemas
# ============================================================================


class StepTypeBlockedBy(SQLModel):
    """The Blocked step type shape shared with the P5 save denial.

    Names the step type only: policy names and scopes are recorded in audit
    events, never shown to the caller (AC-3.g, R11).

    Attributes:
        kind: The step type identifier.
        label: Human-readable step type label.

    """

    kind: str
    label: str


class StepTypePermissionRead(SQLModel):
    """One step type as the calling principal sees it in one project.

    Attributes:
        kind: The step type identifier (a ``NodeType`` value).
        category: Registry grouping (trigger, flow_control or action).
        can_write: The caller's own ``step_type:write`` verdict for this kind
            in the requested project.
        blocked_by: Why the kind is blocked, or ``None`` when it is not.

    """

    kind: str
    category: str
    can_write: bool
    blocked_by: StepTypeBlockedBy | None = None


# ============================================================================
# Helpers
# ============================================================================


async def _project_name(db: AsyncSession, project_id: UUID) -> str:
    """Resolve a project UUID to its name, refusing unknown projects."""
    project = await db.get(Project, project_id)
    if project is None:
        msg = f"Project {project_id} not found"
        raise ProjectNotFoundError(msg)
    return project.name


def _blocked_by(kind: str) -> StepTypeBlockedBy:
    """Build the Blocked step type for one denied kind.

    Treats ``allowed == False`` as blocked even when ``denied`` is false or
    ``denied_by`` is empty: the absence of a matching allow blocks the kind too.
    Policy attribution stays in audit events, not in the response (R11).
    """
    return StepTypeBlockedBy(kind=kind, label=node_kind_display_label(kind))


async def _step_type_verdicts(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
    project_name: str,
) -> list[StepTypePermissionRead]:
    """Evaluate ``step_type:write`` for every registered kind in one pass.

    The effective policies and group memberships are resolved once for the
    action and reused for every kind: only the Rego evaluation differs per
    kind, so one palette open costs one resolution instead of one per kind.
    """
    effective = await resolve_effective_policies(db, user.id, action_filter=ACTION_FILTER)
    groups = await resolve_user_groups(db, user.id)
    entries: list[StepTypePermissionRead] = []
    for kind in _ALL_GRANTABLE_KINDS:
        result = await authorize_resolved(
            evaluator,
            AuthzRequest(
                user_id=user.id,
                action=NODE_ACTION_WRITE,
                resource_type=NODE_RESOURCE_TYPE,
                resource_id=kind,
                resource_labels={"kind": kind},
                resource_project=project_name,
                user_labels=user.labels,
                user_metadata=user.authz_metadata,
            ),
            effective_policies=effective,
            groups=groups,
        )
        entries.append(
            StepTypePermissionRead(
                kind=kind,
                category=_category(kind),
                can_write=result.allowed,
                blocked_by=None if result.allowed else _blocked_by(kind),
            )
        )
    return entries


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    summary="List step types with the caller's write verdicts",
    response_model=list[StepTypePermissionRead],
    dependencies=[NO_PERMISSION],
    operation_id="list_node_kinds",
    response_description="Step type registry with the caller's write verdicts in the project",
)
async def list_node_kinds(
    project_id: Annotated[UUID, Query(description="Project the verdicts are evaluated in")],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
) -> list[StepTypePermissionRead]:
    """List every registered step type with the caller's own write verdicts.

    Requires authentication but no specific permission: the response is scoped
    to the caller and describes reference data plus the caller's own verdicts
    in the requested project. One request evaluates every step type, so the
    add-step panel never needs per-kind ``can_i`` calls.
    """
    project_name = await _project_name(db, project_id)
    return await _step_type_verdicts(db, evaluator, current_user, project_name)
