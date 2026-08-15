"""Role service for CRUD operations."""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import Select, cast, text, type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql._expression_select_cls import SelectOfScalar

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.audit.role_lifecycle import RoleLifecycleEvent
from syntara.authz.exceptions import BuiltinProtectionError, RoleNameConflictError, RoleNotFoundError
from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.models.role import Role
from syntara.authz.role_conventions import (
    BUILTIN_ROLES,
    builtin_role_policy_names,
    builtin_role_uuid,
    get_builtin_policy,
    get_builtin_role,
    is_builtin_policy,
    is_builtin_role,
)
from syntara.authz.schemas import RoleListResponse, RoleRead
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.services.base import BaseService
from syntara.core.utils.filters import Filter, matches_query_param
from syntara.core.utils.sorting import sort_merged_resources

logger = structlog.stdlib.get_logger(__name__)

SelectRole = Select[tuple[Role]] | SelectOfScalar[tuple[Role]]


def _builtin_role_to_read(name: str) -> RoleRead:
    """Convert a builtin role name to a RoleRead schema."""
    info = get_builtin_role(name)
    if not info:
        msg = f"Unknown builtin role: {name}"
        raise ValueError(msg)
    return RoleRead(
        id=builtin_role_uuid(name),
        name=info.name,
        description=info.description,
        policies=builtin_role_policy_names(name),
        is_builtin=info.is_builtin,
        project_id=None,
        scope=info.scope,
        labels={},
        created_at=None,
        updated_at=None,
    )


class RoleService(BaseService):
    """Service for role CRUD operations."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with database session and current user."""
        super().__init__(session, user)

    @staticmethod
    def _get_special_field_handlers() -> dict[str, Any]:
        """Return special field handlers for JSONB policy_name filtering."""

        def handle_policy_name(
            query: SelectRole,
            filter_obj: Filter,
            _model: type[Role],
        ) -> SelectRole:
            if filter_obj.operator.value == "eq":
                col = cast(Role.policy_names, JSONB)
                return query.filter(col.op("@>")(type_coerce([filter_obj.value], JSONB)))
            if filter_obj.operator.value == "contains":
                return query.filter(
                    text(
                        "EXISTS (SELECT 1 FROM jsonb_array_elements_text(policy_names) AS elem"
                        " WHERE elem ILIKE :pattern)"
                    ).params(pattern=f"%{filter_obj.value}%")
                )
            return query

        return {"policy_name": handle_policy_name}

    async def to_role_read(self, role: Role) -> RoleRead:
        """Convert a Role model to a RoleRead schema."""
        return RoleRead(
            id=role.id,
            name=role.name,
            description=role.description,
            policies=role.policy_names,
            is_builtin=role.is_builtin,
            project_id=role.project_id,
            scope=role.scope,
            labels=role.labels,
            created_at=role.created_at,
            updated_at=role.updated_at,
        )

    async def create_role(
        self,
        name: str,
        policies: list[str],
        description: str | None = None,
        labels: dict[str, str] | None = None,
        project_id: UUID | None = None,
    ) -> Role:
        """Create a custom role. Validates that all referenced policy names exist."""
        if project_id is not None:
            from syntara.core.queries.project_queries import assert_project_alive  # noqa: PLC0415

            await assert_project_alive(self.session, project_id)

        if is_builtin_role(name):
            msg = f"Role name '{name}' is reserved for a built-in role"
            raise RoleNameConflictError(msg)
        await self._check_name_conflict(name, project_id)
        await self._validate_policy_names(policies, project_id)

        role = Role(
            name=name,
            description=description,
            is_builtin=False,
            project_id=project_id,
            scope="project" if project_id else "system",
            policy_names=policies,
            labels=labels or {},
        )
        self.session.add(role)
        await self.session.commit()
        await self.session.refresh(role)

        logger.info("Created role", role_id=str(role.id), name=name)
        AuditEventDispatcher.dispatch(
            RoleLifecycleEvent(
                role_id=role.id,
                role_name=role.name,
                action="created",
                project_id=role.project_id,
            ),
        )
        return role

    async def get_role(self, role_id: UUID) -> Role:
        """Get a role by ID."""
        result = await self.session.exec(select(Role).where(Role.id == role_id))
        role = result.first()
        if not role:
            msg = f"Role {role_id} not found"
            raise RoleNotFoundError(msg)
        return role

    def get_role_read(self, role_id: UUID) -> RoleRead | None:
        """Get a builtin role by its deterministic UUID, or None."""
        for r in BUILTIN_ROLES:
            if builtin_role_uuid(r.name) == role_id:
                return _builtin_role_to_read(r.name)
        return None

    async def get_role_or_builtin(self, role_id: UUID) -> RoleRead:
        """Get a role by ID — checks builtins first, then DB."""
        builtin = self.get_role_read(role_id)
        if builtin:
            return builtin
        role = await self.get_role(role_id)
        return await self.to_role_read(role)

    @staticmethod
    def _builtins_first(sort: str | None) -> bool:
        if not sort:
            return True
        field = sort.lstrip("-")
        if field == "is_builtin" and not sort.startswith("-"):
            return False
        return field != "project_id"

    @staticmethod
    def _db_sort(sort: str | None) -> str | None:
        if not sort:
            return None
        field = sort.lstrip("-")
        if field in ("is_builtin", "name", "scope"):
            return None
        return sort

    async def _builtins_first_page(
        self,
        remaining_builtins: list[RoleRead],
        builtin_offset: int,
        limit: int,
        db_cursor: str | None,
        db_sort: str | None,
        query_params_items: Iterable[tuple[str, str]] | None,
        *,
        include_total: bool,
    ) -> RoleListResponse:
        page_builtins = remaining_builtins[:limit]
        db_limit = limit - len(page_builtins)
        more_builtins = len(remaining_builtins) > limit

        needs_db = db_limit > 0 or (not remaining_builtins and not db_cursor)
        needs_total_only = not needs_db and include_total

        if needs_db or needs_total_only:
            db_response = await self.list_resources(
                model=Role,
                response_type=RoleListResponse,
                response_type_converter=lambda r: self._role_to_read(r),
                limit=max(db_limit, 1),
                cursor=db_cursor,
                sort=db_sort,
                query_params_items=query_params_items,
                include_total=include_total,
                special_field_handlers=self._get_special_field_handlers(),
            )
            if not needs_db:
                db_response.resources = []
                db_response.next = None
        else:
            db_response = RoleListResponse(resources=[])

        db_response.resources = [*page_builtins, *db_response.resources]
        if more_builtins:
            db_response.next = f"_b:{builtin_offset + limit}"
        elif db_limit == 0 and not more_builtins and remaining_builtins:
            db_response.next = f"_b:{builtin_offset + len(page_builtins)}"
        return db_response

    async def _builtins_last_page(
        self,
        all_builtins: list[RoleRead],
        remaining_builtins: list[RoleRead],
        builtin_offset: int,
        limit: int,
        db_cursor: str | None,
        db_sort: str | None,
        query_params_items: Iterable[tuple[str, str]] | None,
        *,
        include_total: bool,
    ) -> RoleListResponse:
        db_response = await self.list_resources(
            model=Role,
            response_type=RoleListResponse,
            response_type_converter=lambda r: self._role_to_read(r),
            limit=limit,
            cursor=db_cursor,
            sort=db_sort,
            query_params_items=query_params_items,
            include_total=include_total,
            special_field_handlers=self._get_special_field_handlers(),
        )
        if not db_response.next and remaining_builtins:
            slots = limit - len(db_response.resources)
            new_offset = builtin_offset
            if slots > 0:
                fill = remaining_builtins[:slots]
                db_response.resources.extend(fill)
                new_offset += len(fill)
            if new_offset < len(all_builtins):
                db_response.next = f"_b:{new_offset}"
        return db_response

    async def _list_with_builtins(
        self,
        all_builtins: list[RoleRead],
        limit: int,
        cursor: str | None,
        sort: str | None,
        query_params_items: Iterable[tuple[str, str]] | None,
        *,
        include_total: bool,
    ) -> RoleListResponse:
        """Paginate builtins and DB items together, respecting ``limit``."""
        sort_merged_resources(all_builtins, sort)
        builtins_first = self._builtins_first(sort)
        db_sort = self._db_sort(sort)

        builtin_offset = 0
        db_cursor: str | None = None

        if cursor and cursor.startswith("_b:"):
            builtin_offset = int(cursor[3:])
            if not builtins_first:
                remaining = all_builtins[builtin_offset:]
                page = remaining[:limit]
                nxt = f"_b:{builtin_offset + limit}" if len(remaining) > limit else None
                total: int | None = None
                if include_total:
                    db_count_resp = await self.list_resources(
                        model=Role,
                        response_type=RoleListResponse,
                        response_type_converter=lambda r: self._role_to_read(r),
                        limit=1,
                        query_params_items=query_params_items,
                        include_total=True,
                        special_field_handlers=self._get_special_field_handlers(),
                    )
                    total = (db_count_resp.total or 0) + len(all_builtins)
                return RoleListResponse(resources=page, next=nxt, total=total)
        elif cursor:
            db_cursor = cursor
            if builtins_first:
                builtin_offset = len(all_builtins)

        remaining_builtins = all_builtins[builtin_offset:]

        if builtins_first:
            resp = await self._builtins_first_page(
                remaining_builtins,
                builtin_offset,
                limit,
                db_cursor,
                db_sort,
                query_params_items,
                include_total=include_total,
            )
        else:
            resp = await self._builtins_last_page(
                all_builtins,
                remaining_builtins,
                builtin_offset,
                limit,
                db_cursor,
                db_sort,
                query_params_items,
                include_total=include_total,
            )

        if include_total:
            db_total = resp.total if resp.total is not None else 0
            resp.total = db_total + len(all_builtins)

        sort_merged_resources(resp.resources, sort)
        return resp

    async def list_roles(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> RoleListResponse:
        """List roles with filtering and pagination."""
        excluded_params = {"limit", "cursor", "sort", "include_total"}
        query_params: dict[str, str] = {}
        if query_params_items:
            query_params = {k: v for k, v in query_params_items if k not in excluded_params}

        all_builtins = self._filter_builtin_roles(query_params)
        return await self._list_with_builtins(
            all_builtins,
            limit,
            cursor,
            sort,
            query_params_items,
            include_total=include_total,
        )

    async def list_project_roles(
        self,
        project_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> RoleListResponse:
        """List roles visible within a project."""
        excluded_params = {"limit", "cursor", "sort", "include_total"}
        query_params: dict[str, str] = {}
        if query_params_items:
            query_params = {k: v for k, v in query_params_items if k not in excluded_params}

        all_builtins = self._filter_builtin_roles(query_params, scope_filter="project")
        project_params: Iterable[tuple[str, str]] = [
            *(query_params_items or []),
            ("project_id", str(project_id)),
        ]
        return await self._list_with_builtins(
            all_builtins,
            limit,
            cursor,
            sort,
            project_params,
            include_total=include_total,
        )

    async def update_role(
        self,
        role_id: UUID,
        name: str | None = None,
        description: str | None = None,
        policies: list[str] | None = None,
        labels: dict[str, str] | None = None,
    ) -> Role:
        """Update a role. Builtin roles cannot be updated."""
        if self.get_role_read(role_id):
            msg = "Cannot modify builtin role"
            raise BuiltinProtectionError(msg)

        role = await self.get_role(role_id)
        if role.is_builtin:
            msg = "Cannot modify builtin role"
            raise BuiltinProtectionError(msg)

        if name is not None and name != role.name:
            if is_builtin_role(name):
                msg = f"Role name '{name}' is reserved for a built-in role"
                raise RoleNameConflictError(msg)
            await self._check_name_conflict(name, role.project_id)
            old_name = role.name
            role.name = name
            await self._propagate_role_rename(old_name, name)
        if description is not None:
            role.description = description
        if policies is not None:
            await self._validate_policy_names(policies, role.project_id)
            role.policy_names = policies
        if labels is not None:
            role.labels = labels

        self.session.add(role)
        await self.session.commit()
        await self.session.refresh(role)

        logger.info("Updated role", role_id=str(role_id))
        AuditEventDispatcher.dispatch(
            RoleLifecycleEvent(
                role_id=role.id,
                role_name=role.name,
                action="updated",
                project_id=role.project_id,
            ),
        )
        return role

    async def delete_role(self, role_id: UUID) -> None:
        """Delete a role. Builtin roles cannot be deleted."""
        if self.get_role_read(role_id):
            msg = "Cannot delete builtin role"
            raise BuiltinProtectionError(msg)

        role = await self.get_role(role_id)
        if role.is_builtin:
            msg = "Cannot delete builtin role"
            raise BuiltinProtectionError(msg)

        results = await self.session.exec(select(RoleAssignment).where(RoleAssignment.role_name == role.name))
        assignments = results.all()
        affected_count = len(assignments)
        for row in assignments:
            await self.session.delete(row)

        await self.session.delete(role)
        await self.session.commit()

        logger.info("Deleted role", role_id=str(role_id))
        AuditEventDispatcher.dispatch(
            RoleLifecycleEvent(
                role_id=role.id,
                role_name=role.name,
                action="deleted",
                project_id=role.project_id,
                affected_assignments_count=affected_count,
            ),
        )

    async def _propagate_role_rename(self, old_name: str, new_name: str) -> None:
        """Update all assignments that reference the old role name."""
        results = await self.session.exec(select(RoleAssignment).where(RoleAssignment.role_name == old_name))
        for row in results.all():
            row.role_name = new_name
            self.session.add(row)

    async def _check_name_conflict(self, name: str, project_id: UUID | None) -> None:
        """Check if a role name already exists in the same scope."""
        query = select(Role).where(Role.name == name)
        if project_id is not None:
            query = query.where(Role.project_id == project_id)
        else:
            query = query.where(Role.project_id.is_(None))  # type: ignore[union-attr]
        result = await self.session.exec(query)
        if result.first():
            scope = f"project {project_id}" if project_id else "global scope"
            msg = f"Role '{name}' already exists in {scope}"
            raise RoleNameConflictError(msg)

    async def _validate_policy_names(
        self,
        policy_names: list[str],
        project_id: UUID | None = None,
    ) -> None:
        """Validate that all policy names exist and belong to the correct scope.

        Project-scoped roles may only reference policies from the same project.
        System-scoped roles may only reference global policies.
        """
        from syntara.authz.models.policy import Policy  # noqa: PLC0415

        is_project_role = project_id is not None
        mismatched = []
        for name in policy_names:
            info = get_builtin_policy(name)
            if info is None:
                continue
            is_project_policy = info.scope in ("project", "own")
            if is_project_role != is_project_policy:
                mismatched.append(name)
        if mismatched:
            scope = f"project {project_id}" if is_project_role else "global scope"
            msg = f"Policies not available in {scope}: {', '.join(sorted(mismatched))}"
            raise SafeValueError(msg)

        unknown = [n for n in policy_names if not is_builtin_policy(n)]
        if not unknown:
            return

        query = select(Policy.name, Policy.project_id).where(
            Policy.name.in_(unknown)  # type: ignore[attr-defined]
        )
        if project_id is not None:
            query = query.where(Policy.project_id == project_id)
        else:
            query = query.where(Policy.project_id.is_(None))  # type: ignore[union-attr]

        result = await self.session.exec(query)
        found = {name for name, _ in result.all()}
        still_unknown = [n for n in unknown if n not in found]
        if still_unknown:
            scope = f"project {project_id}" if project_id else "global scope"
            msg = f"Policies not found in {scope}: {', '.join(sorted(still_unknown))}"
            raise SafeValueError(msg)

    @staticmethod
    def _role_to_read(role: Role) -> RoleRead:
        return RoleRead(
            id=role.id,
            name=role.name,
            description=role.description,
            policies=role.policy_names,
            is_builtin=role.is_builtin,
            project_id=role.project_id,
            scope=role.scope,
            labels=role.labels,
            created_at=role.created_at,
            updated_at=role.updated_at,
        )

    @staticmethod
    def _matches_policy_name_filter(
        role_policies: list[str],
        query_params: dict[str, str],
    ) -> bool:
        """Check if any of the role's policies match the policy_name filter."""
        return any(matches_query_param(policy, "policy_name", query_params) for policy in role_policies)

    @staticmethod
    def _filter_builtin_roles(
        query_params: dict[str, str],
        scope_filter: str | None = None,
    ) -> list[RoleRead]:
        """Return builtin roles matching query_params filters."""
        is_builtin_filter = query_params.get("is_builtin")

        effective_scope = scope_filter
        if not effective_scope and query_params.get("project_id"):
            effective_scope = "project"

        has_policy_filter = any(k == "policy_name" or k.startswith("policy_name[") for k in query_params)

        reads = []
        for r in BUILTIN_ROLES:
            if is_builtin_filter == "true" and not r.is_builtin:
                continue
            if is_builtin_filter == "false" and r.is_builtin:
                continue
            if effective_scope and r.scope != effective_scope:
                continue
            if not matches_query_param(r.scope, "scope", query_params):
                continue
            if not matches_query_param(r.name, "name", query_params):
                continue
            if has_policy_filter:
                role_policies = builtin_role_policy_names(r.name)
                if not RoleService._matches_policy_name_filter(role_policies, query_params):
                    continue
            reads.append(_builtin_role_to_read(r.name))
        return reads
