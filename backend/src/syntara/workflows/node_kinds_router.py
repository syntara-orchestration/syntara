"""Node-kind registry and platform-wide kill switch endpoints (ANSTRAT-1750).

Two system-scoped endpoints:

- ``GET /node_kinds`` — the registry as the calling principal sees it: every
  registered kind with its category, whether it is switched on, whether it may
  be switched at all, which actions a deny policy may target, and the caller's
  own ``workflow_node:write`` verdict so the builder can hide or badge palette
  entries.
- ``PUT /node_kinds/{kind}/enabled`` — flips one kind in the
  ``workflows.disabled_node_kinds`` runtime setting.  Requires
  ``setting:write``; the write goes through :class:`SettingsService` so the
  Redis cache invalidation and Pub/Sub fan-out that every API and worker
  process depends on keep working.

The prefix is top-level rather than ``/workflows/node_kinds`` on purpose:
routers are auto-discovered in filesystem order, so a static path nested under
the workflows router could be shadowed by ``/workflows/{workflow_id}``.
"""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, get_authz_evaluator
from syntara.authz.evaluator import AuthzEvaluator
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.settings.services.settings_service import SettingsService
from syntara.workflows.audit.node_kind_switch import NodeKindSwitchEvent
from syntara.workflows.exceptions import NodeKindNotFoundError, NodeKindNotSwitchableError
from syntara.workflows.node_kind_switch import (
    DISABLED_NODE_KINDS_SETTING_KEY,
    get_disabled_node_kinds,
    is_kind_switchable,
    next_disabled_kinds,
)
from syntara.workflows.node_kinds import (
    NODE_ACTION_WRITE,
    NODE_KINDS,
    NodeKindCategory,
    get_node_kind,
)
from syntara.workflows.node_permissions import denied_node_labels

if TYPE_CHECKING:
    from syntara.workflows.node_kinds import NodeKindInfo

router = SyntaraRouter(prefix="/node_kinds", tags=["Node Kinds"])

_require_settings_write = PermissionChecker("setting", "write")


# ============================================================================
# Schemas
# ============================================================================


class NodeKindRead(SQLModel):
    """One workflow node kind as the calling principal sees it.

    Attributes:
        kind: The node kind identifier (a ``NodeType`` value).
        category: Registry grouping (trigger, flow_control or action).
        enabled: False when the kind is switched off platform-wide.
        switchable: Whether this kind may be switched off at all.
        deniable_actions: Actions a deny-effect policy may target for this kind.
        can_write: The caller's own ``workflow_node:write`` verdict for this
            kind with no project in scope.

    """

    kind: str
    category: NodeKindCategory
    enabled: bool
    switchable: bool
    deniable_actions: list[str]
    can_write: bool
    attributes: list["NodeAttributeRead"]


class NodeAttributeRead(SQLModel):
    """One node parameter exposed as an authorization resource label."""

    name: str
    allowed_values: list[str] | None


class NodeKindsListResponse(SQLModel):
    """Response schema for the node-kind registry listing.

    Attributes:
        resources: Every registered kind, in registry declaration order.
        disabled_kinds: Echo of the ``workflows.disabled_node_kinds`` setting.

    """

    resources: list[NodeKindRead]
    disabled_kinds: list[str]


class NodeKindEnabledUpdate(SQLModel):
    """Request body for ``PUT /node_kinds/{kind}/enabled``.

    Attributes:
        enabled: True to switch the kind on, False to switch it off.

    """

    enabled: bool


# ============================================================================
# Helpers
# ============================================================================


def _to_read(info: "NodeKindInfo", *, disabled: frozenset[str], denied_kinds: frozenset[str]) -> NodeKindRead:
    """Build the read model for one registered kind."""
    return NodeKindRead(
        kind=info.kind,
        category=info.category,
        enabled=info.kind not in disabled,
        switchable=is_kind_switchable(info.kind),
        deniable_actions=sorted(info.deniable_actions),
        can_write=info.kind not in denied_kinds,
        attributes=[
            NodeAttributeRead(
                name=attribute.name,
                allowed_values=sorted(attribute.allowed_values) if attribute.allowed_values is not None else None,
            )
            for attribute in info.attributes
        ],
    )


async def _write_denied_kinds(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
) -> frozenset[str]:
    """Return the kinds this caller may not introduce into a workflow.

    Only kinds whose ``write`` action is deniable are evaluated; the rest can
    never be refused, so they are reported as writable without a round trip to
    the policy engine.
    """
    candidates = [info.kind for info in NODE_KINDS if info.is_deniable(NODE_ACTION_WRITE)]
    denials = await denied_node_labels(
        db,
        evaluator,
        user_id=user.id,
        action=NODE_ACTION_WRITE,
        label_sets=[frozenset({("kind", kind)}) for kind in candidates],
        project_name="",
        user_labels=user.labels,
        user_metadata=user.authz_metadata,
    )
    return frozenset(denial.kind for denial in denials)


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    summary="List node kinds",
    response_model=NodeKindsListResponse,
    dependencies=[NO_PERMISSION],
    operation_id="list_node_kinds",
    response_description="Node kind registry with the caller's write verdicts",
)
async def list_node_kinds(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
) -> NodeKindsListResponse:
    """List every registered workflow node kind.

    Requires authentication but no specific permission: the response is scoped
    to the caller and describes reference data plus the caller's own verdicts.
    """
    disabled = await get_disabled_node_kinds()
    denied = await _write_denied_kinds(db, evaluator, current_user)
    return NodeKindsListResponse(
        resources=[_to_read(info, disabled=disabled, denied_kinds=denied) for info in NODE_KINDS],
        disabled_kinds=sorted(disabled),
    )


@router.put(
    "/{kind}/enabled",
    summary="Set node kind enabled",
    response_model=NodeKindRead,
    dependencies=[Depends(_require_settings_write)],
    operation_id="set_node_kind_enabled",
    response_description="The updated node kind",
)
async def set_node_kind_enabled(
    kind: str,
    body: NodeKindEnabledUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
) -> NodeKindRead:
    """Switch one node kind on or off platform-wide.

    Disabling is not a permission: it applies to every principal,
    administrators included. Flow control kinds cannot be switched off.
    """
    info = get_node_kind(kind)
    if info is None:
        raise NodeKindNotFoundError(kind)
    if not is_kind_switchable(kind):
        raise NodeKindNotSwitchableError(kind, info.category.value)

    current = await get_disabled_node_kinds()
    updated = next_disabled_kinds(current, kind, enabled=body.enabled)

    if set(updated) != set(current):
        service = SettingsService(db, current_user)
        await service.update(key=DISABLED_NODE_KINDS_SETTING_KEY, value=updated)
        AuditEventDispatcher.dispatch(
            NodeKindSwitchEvent(
                kind=kind,
                enabled=body.enabled,
                disabled_kinds=updated,
                actor_id=current_user.id,
                actor_username=current_user.username,
            )
        )

    denied = await _write_denied_kinds(db, evaluator, current_user)
    return _to_read(info, disabled=frozenset(updated), denied_kinds=denied)
