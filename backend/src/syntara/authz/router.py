"""Authorization debug/query endpoints.

Provides three query patterns:
- Can I?   — Check if the current user can perform a specific action
- Who can? — List users who can perform a specific action
- What can I? — List all permissions for the current user
- Resource actions — List all available resource types and their valid actions
"""

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, Literal, Self
from uuid import UUID

import structlog
from fastapi import Depends, Query, Request
from pydantic import ConfigDict, model_validator
from pydantic import Field as PydanticField
from sqlalchemy import Select
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.dependencies import get_current_user
from syntara.authz.dependencies import get_authz_evaluator
from syntara.authz.engine import AuthzRequest, authorize, resolve_readable_project_ids
from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.authz.models.project import Project
from syntara.authz.resolver import resolve_effective_policies, resolve_user_groups
from syntara.core.constants import NAME_PATTERN, FieldLimits
from syntara.core.database.session import get_db
from syntara.core.exceptions import SafeValueError
from syntara.core.models.base.query_params import BasePaginatedRequest
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user import User
from syntara.core.services.base import BaseService
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.core.utils.cursor import (
    CursorData,
    PaginationDirection,
    SortDirection,
    create_cursor_data,
    decode_cursor,
    encode_cursor,
    extract_keyset_from_cursor,
    extract_sort_from_cursor,
    serialize_sort_value,
)
from syntara.core.utils.sorting import apply_sorting, parse_sort

logger = structlog.stdlib.get_logger(__name__)

router = SyntaraRouter(prefix="/authz", tags=["Authorization"])


# ============================================================================
# Request/Response Schemas
# ============================================================================


class CanIRequest(SQLModel):
    """Request body for the Can I? authorization check."""

    model_config: ClassVar[ConfigDict] = ConfigDict(title="Can I Request")  # type: ignore[assignment]

    action: str = Field(title=None, description='The action to check (e.g., "read", "create", "delete")')
    resource_type: str = Field(title=None, description='The type of resource (e.g., "workflow", "project")')
    resource_id: str = Field(default="", title=None, description="Optional specific resource ID")
    resource_labels: Annotated[dict[str, str], Field(description="Labels on the target resource")] = {}
    resource_metadata: Annotated[
        dict[str, Any], Field(description="Additional metadata about the target resource")
    ] = {}
    resource_project: str = Field(
        default="", title=None, description="Project scope of the resource (project name or UUID)"
    )
    check_any_project: bool = Field(
        default=False,
        title=None,
        description=(
            "When true, allow if the user has the permission in any project "
            "(project-scoped policies match without a concrete resource_project). "
            "Mutually exclusive with a non-empty resource_project. "
            "Default false preserves strict project matching — empty resource_project "
            "alone is never a wildcard."
        ),
    )

    @model_validator(mode="after")
    def reject_mixed_any_project_and_resource_project(self) -> Self:
        """Reject combining check_any_project with a concrete resource_project."""
        if self.check_any_project and self.resource_project.strip():
            msg = "check_any_project cannot be combined with resource_project; use one or the other"
            raise ValueError(msg)
        return self


class CanIResponse(SQLModel):
    """Authorization decision result."""

    model_config: ClassVar[ConfigDict] = ConfigDict(title="Can I Response")  # type: ignore[assignment]

    allowed: bool = Field(title=None, description="Whether the action is allowed")
    denied: bool = Field(title=None, description="Whether the action is explicitly denied")
    matched_policy: str = Field(title=None, description="Name of the policy that matched")
    denial_reason: str = Field(title=None, description="Reason for denial (empty if allowed)")
    denied_by: str = Field(title=None, description="Name of the deny policy (empty if allowed)")


class WhoCanRequest(BasePaginatedRequest):
    """Request body for the Who can? endpoint."""

    action: str = PydanticField(json_schema_extra={"x-query-param": True})
    resource_type: str = PydanticField(json_schema_extra={"x-query-param": True})
    resource_id: str = PydanticField(default="", json_schema_extra={"x-query-param": True})
    resource_labels: dict[str, str] = PydanticField(default_factory=dict, json_schema_extra={"x-query-param": True})
    resource_metadata: dict[str, Any] = PydanticField(default_factory=dict, json_schema_extra={"x-query-param": True})
    resource_project: str = PydanticField(
        default="",
        description="Project scope of the resource (project name or UUID)",
        json_schema_extra={"x-query-param": True},
    )


class WhoCanUser(SQLModel):
    """A user who can perform the requested action."""

    id: UUID
    username: str


class WhoCanResponse(ResourcesResponse[WhoCanUser]):
    """Paginated response body for the Who can? endpoint."""


class PermissionEntry(SQLModel):
    """A single permission from a policy statement."""

    policy_name: str
    effect: str
    actions: list[str]
    scope: str
    project: str = Field(default="", description="Project scope (empty for system-level)")


class WhatCanIRequest(BasePaginatedRequest):
    """Request body for the What can I? endpoint."""


class WhatCanIResponse(ResourcesResponse[PermissionEntry]):
    """Paginated response body for the What can I? endpoint."""


class ResourceActionsResponse(SQLModel):
    """Available resource types and their valid actions."""

    model_config: ClassVar[ConfigDict] = ConfigDict(title="Resource Actions Response")  # type: ignore[assignment]

    resource_actions: dict[str, list[str]] = Field(description="Map of resource types to their valid actions")


# ============================================================================
# Shared helpers (used by multiple endpoints)
# ============================================================================


async def _resolve_project_input(db: AsyncSession, resource_project: str) -> str:
    """Resolve resource_project: if it's a valid UUID, look up the project name."""
    if not resource_project:
        return ""
    try:
        project_id = UUID(resource_project)
    except ValueError:
        return resource_project
    result = await db.exec(
        select(Project.name).where(
            Project.id == project_id,
            Project.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return result.first() or resource_project


async def _ids_to_names(db: AsyncSession, project_ids: set[UUID]) -> set[str]:
    """Map project UUIDs to their names."""
    projects_result = await db.exec(
        select(Project.name).where(
            Project.id.in_(list(project_ids)),  # type: ignore[attr-defined]
            Project.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return set(projects_result.all())


# ============================================================================
# what_can_i helpers
# ============================================================================

_WHAT_CAN_I_SORTABLE_FIELDS: list[str] = ["policy_name", "effect", "scope"]


def _is_cursor_stale(
    cursor_data: CursorData,
    cursor_index: int | None,
    sorted_items: list[PermissionEntry],
    sort_field: str,
) -> bool:
    """Detect if the in-memory list changed between paginated requests.

    what_can_i paginates an in-memory list using index-based cursors. If
    the underlying data changes (e.g., a role assignment is added or removed),
    the same index may point to a different item. This compares the stored
    sort value in the cursor against the current value at that index; a
    mismatch resets pagination to page 1.
    """
    if cursor_index is None:
        return False
    if not (0 <= cursor_index < len(sorted_items)):
        return True
    stored = cursor_data.get("created_at")
    if stored is None:
        return False
    return str(getattr(sorted_items[cursor_index], sort_field)) != stored


def _parse_what_can_i_cursor(
    cursor: str,
    sort_field: str,
    sort_direction: SortDirection,
) -> tuple[CursorData, int | None, str, SortDirection, PaginationDirection]:
    """Decode a what_can_i cursor string into its components."""
    cursor_data = decode_cursor(cursor)

    sort_field_c, sort_direction_c = extract_sort_from_cursor(cursor_data)
    if sort_field_c and sort_field_c in _WHAT_CAN_I_SORTABLE_FIELDS:
        sort_field = sort_field_c
        sort_direction = sort_direction_c

    raw_id = cursor_data.get("id")
    try:
        cursor_index = int(raw_id) if raw_id else None
    except (ValueError, TypeError):
        cursor_index = None

    dir_str = cursor_data.get("direction", "next")
    direction = PaginationDirection.PREV if dir_str == "prev" else PaginationDirection.NEXT

    return cursor_data, cursor_index, sort_field, sort_direction, direction


def _slice_page(
    sorted_items: list[PermissionEntry],
    cursor_index: int | None,
    direction: PaginationDirection,
    limit: int,
) -> tuple[list[PermissionEntry], int]:
    """Select the page slice and return (page, start_index)."""
    if cursor_index is None:
        return sorted_items[:limit], 0
    if direction == PaginationDirection.NEXT:
        start = cursor_index + 1
        return sorted_items[start : start + limit], start
    end = cursor_index
    start = max(0, end - limit)
    return sorted_items[start:end], start


def _paginate_in_memory(
    items: list[PermissionEntry],
    *,
    sort_field: str,
    sort_direction: SortDirection,
    limit: int,
    cursor: str | None,
    include_total: bool,
) -> WhatCanIResponse:
    """Sort and paginate an in-memory list of PermissionEntry items.

    Uses index-based cursor positioning: the cursor encodes the index of the
    boundary item in the sorted list plus the sort parameters. On subsequent
    requests the list is re-sorted identically and the index is used to slice.
    """
    if not items:
        return WhatCanIResponse(resources=[], next=None, prev=None, total=0 if include_total else None)

    cursor_index: int | None = None
    direction = PaginationDirection.NEXT
    cursor_data: CursorData = {}

    if cursor:
        cursor_data, cursor_index, sort_field, sort_direction, direction = _parse_what_can_i_cursor(
            cursor, sort_field, sort_direction
        )

    reverse = sort_direction == SortDirection.DESC
    sorted_items = sorted(
        items,
        key=lambda p: (getattr(p, sort_field), p.policy_name, p.effect, p.scope, p.project),
        reverse=reverse,
    )

    if cursor and _is_cursor_stale(cursor_data, cursor_index, sorted_items, sort_field):
        cursor_index = None
        direction = PaginationDirection.NEXT

    total_count = len(sorted_items) if include_total else None
    page, start_index = _slice_page(sorted_items, cursor_index, direction, limit)

    if not page:
        return WhatCanIResponse(resources=[], next=None, prev=None, total=total_count)

    page_end_index = start_index + len(page) - 1
    has_next = page_end_index < len(sorted_items) - 1
    has_prev = start_index > 0

    def _make_cursor(index: int, nav_direction: PaginationDirection) -> str:
        sort_value = str(getattr(sorted_items[index], sort_field))
        return encode_cursor(
            create_cursor_data(
                resource_id=str(index),
                created_at=sort_value,
                direction=nav_direction,
                sort_field=sort_field,
                sort_direction=sort_direction,
            )
        )

    next_cursor = _make_cursor(page_end_index, PaginationDirection.NEXT) if has_next else None
    prev_cursor = _make_cursor(start_index, PaginationDirection.PREV) if has_prev else None

    return WhatCanIResponse(resources=page, next=next_cursor, prev=prev_cursor, total=total_count)


# ============================================================================
# who_can helpers
# ============================================================================

# who_can can't use BaseService for pagination because authorization is determined
# per-user via the evaluator, not by SQL filters. We must scan users in batches,
# check each against the evaluator, and paginate the filtered results manually.
_WHO_CAN_SORTABLE_FIELDS: list[str] = ["id", "username"]
_WHO_CAN_DB_BATCH_SIZE = 200
_WHO_CAN_MAX_TOTAL_SCAN = 10_000


async def _check_user_authorized(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
    body: WhoCanRequest,
    resource_project: str,
) -> bool:
    """Check if a single user is authorized for the requested action."""
    result = await authorize(
        db,
        evaluator,
        AuthzRequest(
            user_id=user.id,
            action=body.action,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            resource_labels=body.resource_labels,
            resource_metadata=body.resource_metadata,
            resource_project=resource_project,
            user_labels=user.labels,
            user_metadata=user.authz_metadata,
        ),
    )
    return result.allowed


def _apply_who_can_cursor_filter(
    query: Select[tuple[User]],
    *,
    sort_field: str,
    sort_direction: SortDirection,
    direction: PaginationDirection,
    cursor_id: UUID,
    cursor_sort_value: str | None,
) -> Select[tuple[User]]:
    """Apply cursor boundary filter for who_can pagination."""
    if sort_field == "id":
        if (direction == PaginationDirection.NEXT) == (sort_direction == SortDirection.ASC):
            return query.where(col(User.id) > cursor_id)
        return query.where(col(User.id) < cursor_id)

    if cursor_sort_value is None:
        return query

    filtered, _needs_reverse = BaseService._apply_keyset_filter(  # noqa: SLF001
        query,
        col(getattr(User, sort_field)),
        cursor_sort_value,
        col(User.id),
        cursor_id,
        sort_direction,
        direction,
    )
    return filtered  # type: ignore[return-value]


async def _check_batch_authorization(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    batch: Sequence[User],
    body: WhoCanRequest,
    resource_project: str,
    authorized: list[WhoCanUser],
    checked_ids: set[UUID],
    target_count: int,
) -> None:
    """Check each user in a batch against OPA, appending authorized ones."""
    for user in batch:
        checked_ids.add(user.id)
        if await _check_user_authorized(db, evaluator, user, body, resource_project):
            authorized.append(WhoCanUser(id=user.id, username=user.username))
            if len(authorized) >= target_count:
                return


async def _scan_authorized_users(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    body: WhoCanRequest,
    resource_project: str,
    *,
    cursor_id: UUID | None,
    cursor_sort_value: str | None,
    direction: PaginationDirection,
    sort_field: str,
    sort_direction: SortDirection,
    target_count: int,
) -> tuple[list[WhoCanUser], set[UUID]]:
    """Scan users in batches and return those authorized for the action.

    Checks each user against OPA one at a time and stops as soon as
    target_count authorized users are found or all matching users have
    been checked.

    Returns:
        Tuple of (authorized_users, checked_user_ids). The checked set
        includes all users evaluated against OPA (authorized or not),
        allowing callers to skip redundant OPA checks.

    """
    authorized: list[WhoCanUser] = []
    checked_ids: set[UUID] = set()
    batch_cursor_id = cursor_id
    batch_sort_value = cursor_sort_value
    is_backward = direction == PaginationDirection.PREV
    reversed_direction = SortDirection.ASC if sort_direction == SortDirection.DESC else SortDirection.DESC
    actual_direction = reversed_direction if is_backward else sort_direction

    while len(authorized) < target_count:
        query = select(User).where(
            User.is_enabled.is_(True),  # type: ignore[attr-defined]
            User.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        if batch_cursor_id is not None:
            query = _apply_who_can_cursor_filter(  # type: ignore[assignment]
                query,
                sort_field=sort_field,
                sort_direction=sort_direction,
                direction=direction,
                cursor_id=batch_cursor_id,
                cursor_sort_value=batch_sort_value,
            )
        query = apply_sorting(  # type: ignore[assignment]
            query,
            [(sort_field, actual_direction), ("id", actual_direction)],
            User,
        )
        query = query.limit(_WHO_CAN_DB_BATCH_SIZE)

        users_result = await db.exec(query)
        batch = users_result.all()
        if not batch:
            break

        await _check_batch_authorization(
            db, evaluator, batch, body, resource_project, authorized, checked_ids, target_count
        )

        last = batch[-1]
        batch_cursor_id = last.id
        batch_sort_value = serialize_sort_value(getattr(last, sort_field)) if sort_field != "id" else None

    if is_backward:
        authorized.reverse()
    return authorized, checked_ids


def _log_scan_cap_exceeded(count_so_far: int) -> None:
    logger.warning(
        "who_can total count scan exceeded safety cap",
        cap=_WHO_CAN_MAX_TOTAL_SCAN,
        count_so_far=count_so_far,
    )


async def _count_batch_authorized(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    batch: Sequence[User],
    body: WhoCanRequest,
    resource_project: str,
    already_checked: set[UUID],
    count: int,
    users_scanned: int,
) -> tuple[int, int, bool]:
    """Count authorized users in a single batch.

    Returns (updated_count, updated_users_scanned, cap_exceeded).
    """
    for user in batch:
        users_scanned += 1
        if users_scanned > _WHO_CAN_MAX_TOTAL_SCAN:
            _log_scan_cap_exceeded(count)
            return count, users_scanned, True
        if user.id in already_checked:
            continue
        if await _check_user_authorized(db, evaluator, user, body, resource_project):
            count += 1
    return count, users_scanned, False


async def _count_authorized_users(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    body: WhoCanRequest,
    resource_project: str,
    *,
    skip_ids: set[UUID] | None = None,
    initial_count: int = 0,
) -> int | None:
    """Count all users authorized for the action.

    Scans all active users and checks each against the evaluator. Capped at
    _WHO_CAN_MAX_TOTAL_SCAN users to prevent runaway queries on
    large user bases. Returns None when the cap is reached, signaling
    that the total is indeterminate.

    When ``skip_ids`` is provided, users already evaluated by a prior
    scan are skipped to avoid redundant evaluator calls. ``initial_count``
    seeds the counter with authorized users already known.
    """
    count = initial_count
    users_scanned = 0
    scan_cursor: UUID | None = None
    already_checked = skip_ids or set()

    while True:
        query = (
            select(User)
            .where(
                User.is_enabled.is_(True),  # type: ignore[attr-defined]
                User.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .order_by(col(User.id))
            .limit(_WHO_CAN_DB_BATCH_SIZE)
        )
        if scan_cursor:
            query = query.where(col(User.id) > scan_cursor)

        users_result = await db.exec(query)
        batch = users_result.all()
        if not batch:
            break

        count, users_scanned, cap_exceeded = await _count_batch_authorized(
            db, evaluator, batch, body, resource_project, already_checked, count, users_scanned
        )
        if cap_exceeded:
            return None

        scan_cursor = batch[-1].id

    return count


def _build_page_cursors(
    results: list[WhoCanUser],
    *,
    direction: PaginationDirection,
    has_more: bool,
    cursor_id: UUID | None,
    sort_field: str,
    sort_direction: SortDirection,
) -> tuple[str | None, str | None]:
    """Build next/prev cursor strings from a page of results.

    Emits a next cursor when there are more results ahead, and a prev
    cursor when there are results behind (i.e., we didn't start from
    the beginning). Each cursor encodes the boundary user's sort value,
    id, sort field, sort direction, and navigation direction.
    """
    if not results:
        return None, None

    is_forward = direction == PaginationDirection.NEXT

    def _make_cursor(boundary: WhoCanUser, nav_direction: PaginationDirection) -> str:
        sv = serialize_sort_value(getattr(boundary, sort_field)) if sort_field != "id" else None
        return encode_cursor(
            create_cursor_data(
                resource_id=boundary.id,
                sort_value=sv,
                direction=nav_direction,
                sort_field=sort_field,
                sort_direction=sort_direction,
            )
        )

    # next cursor: emit when forward and there are more rows, or backward and
    # we know there are rows ahead (because we started from a cursor, not the beginning)
    if (is_forward and has_more) or (not is_forward and cursor_id is not None):
        next_cursor = _make_cursor(results[-1], PaginationDirection.NEXT)
    else:
        next_cursor = None

    # prev cursor: emit when forward and we started from a cursor (not page 1),
    # or backward and there are more rows behind us
    if (is_forward and cursor_id is not None) or (not is_forward and has_more):
        prev_cursor = _make_cursor(results[0], PaginationDirection.PREV)
    else:
        prev_cursor = None

    return next_cursor, prev_cursor


# ============================================================================
# Authorization Helpers
# ============================================================================


async def _user_has_authz_query_permission(
    user: User,
    evaluator: AuthzEvaluator,
    db: AsyncSession,
) -> bool:
    """Check if user has system-level authz:query permission.

    Used as fallback for ad-hoc who_can queries without a resource_id.
    Only admins (those with system-level authz:query) can make these queries.
    """
    result = await authorize(
        db,
        evaluator,
        AuthzRequest(
            user_id=user.id,
            action="query",
            resource_type="authz",
            resource_id="",
            user_labels=user.labels,
            user_metadata=user.authz_metadata,
        ),
    )
    return result.allowed


async def _can_edit_workflow_in_project(
    user: User,
    evaluator: AuthzEvaluator,
    db: AsyncSession,
    resource_project: str,
) -> bool:
    """Check if user can create or update workflows in the given project."""
    for action in ("update", "create"):
        result = await authorize(
            db,
            evaluator,
            AuthzRequest(
                user_id=user.id,
                action=action,
                resource_type="workflow",
                resource_id="",
                resource_project=resource_project,
                user_labels=user.labels,
                user_metadata=user.authz_metadata,
            ),
        )
        if result.allowed:
            return True
    return False


@dataclass(frozen=True)
class _WhoCanGateRule:
    """Maps a (resource_type, action) query pair to its required permission check."""

    resource_type: str
    action: str
    check: Callable[[User, AuthzEvaluator, AsyncSession, str], Awaitable[bool]]


_WHO_CAN_GATE_RULES: tuple[_WhoCanGateRule, ...] = (
    _WhoCanGateRule("approval", "decide", _can_edit_workflow_in_project),
)

_WHO_CAN_GATE_LOOKUP: dict[tuple[str, str], _WhoCanGateRule] = {
    (r.resource_type, r.action): r for r in _WHO_CAN_GATE_RULES
}


def _dispatch_who_can_denied(current_user: User, body: WhoCanRequest) -> None:
    """Dispatch an audit event for a denied who_can query."""
    from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
    from syntara.authz.audit.authorization_denied import AuthorizationDeniedEvent  # noqa: PLC0415

    AuditEventDispatcher.dispatch(
        AuthorizationDeniedEvent(
            user_id=current_user.id,
            username=current_user.username,
            resource_id=body.resource_id,
            resource_type=body.resource_type,
            resource_name="",
            action=body.action,
            denied_by="who_can_gate",
            principal_type=current_user.__dict__.get("__principal_type__"),
        )
    )
    logger.info(
        "Authorization denied for who_can query",
        user_id=str(current_user.id),
        resource_type=body.resource_type,
        action=body.action,
    )


async def _enforce_who_can_permission(
    body: WhoCanRequest,
    current_user: User,
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    resource_project: str,
    request: Request,
) -> bool:
    """Enforce two-tier authorization gate for who_can queries.

    Tier 0 (always): authz:query holders (admins, CLI) pass unconditionally,
            preserving backwards compatibility with the old PermissionChecker gate.
    Tier 1: resource_project provided — the query's (resource_type, action)
            pair must match a gate rule in _WHO_CAN_GATE_RULES, and the user
            must pass that rule's permission check. Each rule binds the
            allowed query pair to its required permission, so adding a new
            pair forces the developer to specify how it is authorized.
    Tier 2: No project context and no authz:query — denied.

    Certificate-authenticated requests (service-to-service) bypass the gate,
    matching the behavior of PermissionChecker.

    Client-supplied resource_labels/resource_metadata are NOT used in the gate
    to prevent forged attributes from influencing authorization.

    Returns:
        True if the caller is fully trusted (admin or cert-auth) and may
        supply arbitrary query parameters including resource_labels/metadata.
        False if the caller passed via a scoped gate rule (Tier 1) and
        client-supplied labels/metadata should be stripped.

    """
    if getattr(request.state, "is_cert_authenticated", False):
        return True

    if await _user_has_authz_query_permission(current_user, evaluator, db):
        return True

    if resource_project:
        query_pair = (body.resource_type, body.action)
        rule = _WHO_CAN_GATE_LOOKUP.get(query_pair)
        if rule is None:
            msg = f"who_can query for {body.resource_type}:{body.action} is not permitted for non-admin users"
            _dispatch_who_can_denied(current_user, body)
            raise AuthorizationDeniedError(msg)

        if not await rule.check(current_user, evaluator, db, resource_project):
            msg = f"Not authorized to query {body.resource_type} in project {resource_project}"
            _dispatch_who_can_denied(current_user, body)
            raise AuthorizationDeniedError(msg)

        return False

    msg = "System-wide who_can queries require authz:query permission"
    _dispatch_who_can_denied(current_user, body)
    raise AuthorizationDeniedError(msg)


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/can_i",
    dependencies=[NO_PERMISSION],
    operation_id="can_i",
    summary="Check if the current user can perform an action",
    description=(
        "Evaluates the current user's effective policies to determine if a specific action is allowed on a resource."
    ),
    response_description="Authorization decision",
)
async def can_i(
    body: CanIRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
) -> CanIResponse:
    """Check if the current user can perform a specific action.

    Evaluates the user's effective policies against the configured authz evaluator.

    Args:
        body: The authorization query.
        current_user: The authenticated user.
        db: Database session.
        evaluator: Authorization evaluator.

    Returns:
        Authorization decision.

    """
    resource_project = await _resolve_project_input(db, body.resource_project)

    result = await authorize(
        db,
        evaluator,
        AuthzRequest(
            user_id=current_user.id,
            action=body.action,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            resource_labels=body.resource_labels,
            resource_metadata=body.resource_metadata,
            resource_project=resource_project,
            check_any_project=body.check_any_project,
            user_labels=current_user.labels,
            user_metadata=current_user.authz_metadata,
        ),
    )

    return CanIResponse(
        allowed=result.allowed,
        denied=result.denied,
        matched_policy=result.matched_policy,
        denial_reason=result.denial_reason,
        denied_by=result.denied_by,
    )


@router.post(
    "/who_can",
    dependencies=[NO_PERMISSION],
    operation_id="who_can",
    summary="List users who can perform an action",
    description=(
        "Iterates all active users, resolves their policies, and checks each against the configured authz evaluator."
    ),
    response_description="List of authorized users",
)
async def who_can(
    request: Request,
    body: WhoCanRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
) -> WhoCanResponse:
    """List users who can perform a specific action.

    Two-tier authorization model:
    1. resource_project provided — the (resource_type, action) pair must match
       a gate rule, and the user must pass that rule's permission check
       (e.g. workflow:update for approval:decide queries).
    2. No resource_project — system-wide query, requires authz:query (admin).

    Args:
        request: The HTTP request (used for cert-auth bypass check).
        body: Query parameters including action, resource_type, optional resource_id.
        current_user: Authenticated user (permission check happens inside).
        db: Database session.
        evaluator: Authorization evaluator.

    Returns:
        Paginated list of users who can perform the action.

    Raises:
        AuthorizationDeniedError: If user lacks permission for this query type.

    """
    resource_project = await _resolve_project_input(db, body.resource_project)
    is_trusted = await _enforce_who_can_permission(body, current_user, db, evaluator, resource_project, request)

    if not is_trusted:
        # Tier 1 callers must not influence per-user OPA evaluation with
        # forged labels/metadata — only admins and cert-auth may supply them.
        # Use model_copy to avoid mutating the original request body.
        body = body.model_copy(update={"resource_labels": {}, "resource_metadata": {}})

    if body.cursor:
        cursor_data = decode_cursor(body.cursor)
        sort_field_c, cursor_sort_value, resource_id, _created_at, direction = extract_keyset_from_cursor(cursor_data)
        cursor_id = UUID(resource_id) if resource_id else None
        _, sort_direction = extract_sort_from_cursor(cursor_data)
        sort_field = sort_field_c or "id"
        if sort_field not in _WHO_CAN_SORTABLE_FIELDS:
            msg = f"Invalid sort field in cursor: {sort_field}"
            raise SafeValueError(msg)
    else:
        sort_field, sort_direction = parse_sort(
            body.sort, _WHO_CAN_SORTABLE_FIELDS, default_field="id", default_direction=SortDirection.ASC
        )
        cursor_id, cursor_sort_value, direction = None, None, PaginationDirection.NEXT

    results, checked_ids = await _scan_authorized_users(
        db,
        evaluator,
        body,
        resource_project,
        cursor_id=cursor_id,
        cursor_sort_value=cursor_sort_value,
        direction=direction,
        sort_field=sort_field,
        sort_direction=sort_direction,
        target_count=body.limit + 1,
    )

    page_authorized_count = len(results)
    has_more = len(results) > body.limit
    if has_more:
        results = results[1:] if direction == PaginationDirection.PREV else results[: body.limit]

    next_cursor, prev_cursor = _build_page_cursors(
        results,
        direction=direction,
        has_more=has_more,
        cursor_id=cursor_id,
        sort_field=sort_field,
        sort_direction=sort_direction,
    )

    total_count: int | None = None
    if body.include_total:
        logger.info(
            "who_can include_total requested — scanning up to %d users",
            _WHO_CAN_MAX_TOTAL_SCAN,
            action=body.action,
            resource_type=body.resource_type,
        )
        total_count = await _count_authorized_users(
            db,
            evaluator,
            body,
            resource_project,
            skip_ids=checked_ids,
            initial_count=page_authorized_count,
        )

    return WhoCanResponse(
        resources=results,
        next=next_cursor,
        prev=prev_cursor,
        total=total_count,
    )


@router.post(
    "/what_can_i",
    dependencies=[NO_PERMISSION],
    operation_id="what_can_i",
    summary="List all permissions for the current user",
    description=(
        "Resolves the current user's effective policies and returns them as a flat list of permission entries."
        " No runtime policy evaluation call is needed."
    ),
    response_description="Paginated list of permission entries",
)
async def what_can_i(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: WhatCanIRequest,
) -> WhatCanIResponse:
    """List all permissions for the current user.

    Resolves the user's effective policies and returns them as a
    flat list of permission entries. No policy evaluation call is needed.

    Args:
        request: The HTTP request.
        current_user: The authenticated user.
        db: Database session.
        body: Request body specifying query parameters.

    Returns:
        List of permission entries.

    """
    effective = await resolve_effective_policies(db, current_user.id)
    groups = await resolve_user_groups(db, current_user.id)

    evaluator = get_authz_evaluator(request)
    readable_ids = await resolve_readable_project_ids(
        db,
        evaluator,
        current_user.id,
        effective,
        groups,
        current_user.labels,
        current_user.authz_metadata,
    )
    readable_names: set[str] | None = None
    if readable_ids is not None:
        readable_names = await _ids_to_names(db, readable_ids) if readable_ids else set()

    permissions = [
        PermissionEntry(
            policy_name=p.get("name", ""),
            effect=p.get("effect", ""),
            actions=p.get("actions", []),
            scope=p.get("scope", ""),
            project=p.get("project", "") if readable_names is None or p.get("project", "") in readable_names else "",
        )
        for p in effective
    ]

    sort_field, sort_direction = parse_sort(
        body.sort, _WHAT_CAN_I_SORTABLE_FIELDS, default_field="policy_name", default_direction=SortDirection.ASC
    )

    return _paginate_in_memory(
        items=permissions,
        sort_field=sort_field,
        sort_direction=sort_direction,
        limit=body.limit,
        cursor=body.cursor,
        include_total=body.include_total,
    )


@router.get(
    "/resource_actions",
    dependencies=[NO_PERMISSION],
    operation_id="get_resource_actions",
    summary="List available resource types and actions",
    description="Returns the catalog of all resource types and the actions that can be performed on each.",
    response_description="Map of resource types to their valid actions",
)
async def get_resource_actions(request: Request) -> ResourceActionsResponse:
    """Return the canonical resource-type -> actions catalog.

    Built dynamically at startup from route dependencies and built-in policies.
    """
    return ResourceActionsResponse(resource_actions=request.app.state.resource_actions)


# ============================================================================
# Name validation
# ============================================================================

_NAME_RE = re.compile(NAME_PATTERN)


class ValidateNameResponse(SQLModel):
    """Response body for the validate_name endpoint."""

    valid: bool
    name: str
    reason: str = ""


@router.get("/validate_name", summary="Validate name", dependencies=[NO_PERMISSION], operation_id="validate_name")
async def validate_name(
    name: Annotated[str, Query(description="Name to validate")],
    resource_type: Annotated[  # noqa: ARG001
        Literal["project", "policy", "role"],
        Query(description="Resource type"),
    ] = "project",
) -> ValidateNameResponse:
    """Validate a resource name against naming rules.

    Returns whether the name is valid and, if not, why.
    Intended for real-time UI validation.
    """
    if not name:
        return ValidateNameResponse(valid=False, name=name, reason="Name must not be empty")
    if len(name) > FieldLimits.NAME_MAX_LENGTH:
        return ValidateNameResponse(
            valid=False, name=name, reason=f"Name must be {FieldLimits.NAME_MAX_LENGTH} characters or fewer"
        )
    if not _NAME_RE.match(name):
        return ValidateNameResponse(
            valid=False,
            name=name,
            reason="Name must start and end with a letter or digit, "
            "and may contain letters, digits, colons, hyphens, and underscores",
        )

    return ValidateNameResponse(valid=True, name=name)
