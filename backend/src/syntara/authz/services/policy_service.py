"""Policy service for CRUD operations."""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.audit.policy_lifecycle import PolicyLifecycleEvent
from syntara.authz.exceptions import (
    BuiltinProtectionError,
    DenyEffectNotSupportedError,
    InvalidResourceActionError,
    PolicyNameConflictError,
    PolicyNotFoundError,
)
from syntara.authz.models.policy import Policy
from syntara.authz.role_conventions import (
    BUILTIN_POLICIES,
    builtin_policy_uuid,
    get_builtin_policy,
    is_builtin_policy,
)
from syntara.authz.schemas import PolicyListResponse, PolicyRead
from syntara.core.models import User
from syntara.core.services.base import BaseService
from syntara.core.utils.filters import matches_query_param
from syntara.core.utils.sorting import sort_merged_resources

logger = structlog.stdlib.get_logger(__name__)


def _builtin_policy_to_read(name: str) -> PolicyRead | None:
    """Convert a builtin policy name to a PolicyRead schema."""
    info = get_builtin_policy(name)
    if not info:
        return None
    return PolicyRead(
        id=builtin_policy_uuid(name),
        name=info.name,
        description=info.description,
        statements=info.statements,
        is_builtin=True,
        project_id=None,
        scope=info.scope,
        labels={},
        created_at=None,
        updated_at=None,
    )


class PolicyService(BaseService):
    """Service for policy CRUD operations."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with database session and current user."""
        super().__init__(session, user)

    @staticmethod
    def _validate_resource_actions(statements: list[dict[str, Any]]) -> None:
        """Reject statements that reference unregistered resource:action pairs."""
        from syntara.authz.resource_actions import validate_statements  # noqa: PLC0415

        invalid = validate_statements(statements)
        if invalid:
            msg = f"Unregistered resource:action pairs: {', '.join(invalid)}"
            raise InvalidResourceActionError(msg)

    @staticmethod
    def _validate_no_deny_effect(statements: list[dict[str, Any]]) -> None:
        """Reject deny-effect statements (AAP-74620).

        Deny-effect policies are not yet supported. A project-scoped deny
        can lock out higher-privileged users because deny unconditionally
        overrides allow in Rego. Re-enable when scoped deny controls are
        implemented (e.g. admin-only via policy:create-deny permission).
        """
        if any(s.get("effect") == "deny" for s in statements):
            msg = "Deny-effect policies are not supported. Use allow-effect policies only."
            raise DenyEffectNotSupportedError(msg)

    @staticmethod
    def _validate_project_statements(statements: list[dict[str, Any]]) -> None:
        """Reject statements invalid for project-scoped policies."""
        from syntara.authz.resource_actions import validate_project_statements  # noqa: PLC0415

        error = validate_project_statements(statements)
        if error:
            raise InvalidResourceActionError(error)

    async def create_policy(
        self,
        name: str,
        statements: list[dict[str, Any]],
        description: str | None = None,
        labels: dict[str, str] | None = None,
        project_id: UUID | None = None,
    ) -> Policy:
        """Create a custom policy."""
        if project_id is not None:
            from syntara.core.queries.project_queries import assert_project_alive  # noqa: PLC0415

            await assert_project_alive(self.session, project_id)

        self._validate_no_deny_effect(statements)
        self._validate_resource_actions(statements)
        if project_id is not None:
            self._validate_project_statements(statements)
        if is_builtin_policy(name):
            msg = f"Policy name '{name}' is reserved for a built-in policy"
            raise PolicyNameConflictError(msg)
        await self._check_name_conflict(name, project_id)

        scope = "any"
        for s in statements:
            if s.get("scope") in ("project", "self"):
                scope = s["scope"]
                break

        policy = Policy(
            name=name,
            description=description,
            statements=statements,
            is_builtin=False,
            project_id=project_id,
            scope=scope,
            labels=labels or {},
        )
        self.session.add(policy)
        await self.session.commit()
        await self.session.refresh(policy)

        logger.info("Created policy", policy_id=str(policy.id), name=name)
        AuditEventDispatcher.dispatch(
            PolicyLifecycleEvent(
                policy_id=policy.id,
                policy_name=policy.name,
                action="created",
                project_id=policy.project_id,
            ),
        )
        return policy

    async def get_policy(self, policy_id: UUID) -> Policy:
        """Get a policy by ID (custom policies only)."""
        result = await self.session.exec(select(Policy).where(Policy.id == policy_id))
        policy = result.first()
        if not policy:
            msg = f"Policy {policy_id} not found"
            raise PolicyNotFoundError(msg)
        return policy

    def get_policy_read(self, policy_id: UUID) -> PolicyRead | None:
        """Get a builtin policy by its deterministic UUID, or None."""
        for p in BUILTIN_POLICIES:
            if builtin_policy_uuid(p.name) == policy_id:
                return _builtin_policy_to_read(p.name)
        return None

    async def get_policy_or_builtin(self, policy_id: UUID) -> PolicyRead:
        """Get a policy by ID — checks builtins first, then DB."""
        builtin = self.get_policy_read(policy_id)
        if builtin:
            return builtin
        policy = await self.get_policy(policy_id)
        return PolicyRead.model_validate(policy)

    @staticmethod
    def _builtins_first(sort: str | None) -> bool:
        """Return True when builtins should appear before DB items."""
        if not sort:
            return True
        field = sort.lstrip("-")
        if field == "is_builtin" and not sort.startswith("-"):
            return False
        return field != "project_id"

    @staticmethod
    def _db_sort(sort: str | None) -> str | None:
        """Normalize sort for DB queries.

        The base pagination cursor always encodes ``created_at``, so sorting
        by other fields (``is_builtin``, ``name``, ``scope``) causes cursor
        mismatches. Fall back to default sort for those fields and handle
        the ordering via the builtin/DB split + within-page sort.
        """
        if not sort:
            return None
        field = sort.lstrip("-")
        if field in ("is_builtin", "name", "scope"):
            return None
        return sort

    async def _builtins_first_page(
        self,
        remaining_builtins: list[PolicyRead],
        builtin_offset: int,
        limit: int,
        db_cursor: str | None,
        db_sort: str | None,
        query_params_items: Iterable[tuple[str, str]] | None,
        *,
        include_total: bool,
    ) -> PolicyListResponse:
        page_builtins = remaining_builtins[:limit]
        db_limit = limit - len(page_builtins)
        more_builtins = len(remaining_builtins) > limit

        needs_db = db_limit > 0 or (not remaining_builtins and not db_cursor)
        needs_total_only = not needs_db and include_total

        if needs_db or needs_total_only:
            db_response = await self.list_resources(
                model=Policy,
                response_type=PolicyListResponse,
                response_type_converter=PolicyRead.model_validate,
                limit=max(db_limit, 1),
                cursor=db_cursor,
                sort=db_sort,
                query_params_items=query_params_items,
                include_total=include_total,
            )
            if not needs_db:
                db_response.resources = []
                db_response.next = None
        else:
            db_response = PolicyListResponse(resources=[])

        db_response.resources = [*page_builtins, *db_response.resources]
        if more_builtins:
            db_response.next = f"_b:{builtin_offset + limit}"
        elif db_limit == 0 and not more_builtins and remaining_builtins:
            db_response.next = f"_b:{builtin_offset + len(page_builtins)}"
        return db_response

    async def _builtins_last_page(
        self,
        all_builtins: list[PolicyRead],
        remaining_builtins: list[PolicyRead],
        builtin_offset: int,
        limit: int,
        db_cursor: str | None,
        db_sort: str | None,
        query_params_items: Iterable[tuple[str, str]] | None,
        *,
        include_total: bool,
    ) -> PolicyListResponse:
        db_response = await self.list_resources(
            model=Policy,
            response_type=PolicyListResponse,
            response_type_converter=PolicyRead.model_validate,
            limit=limit,
            cursor=db_cursor,
            sort=db_sort,
            query_params_items=query_params_items,
            include_total=include_total,
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
        all_builtins: list[PolicyRead],
        limit: int,
        cursor: str | None,
        sort: str | None,
        query_params_items: Iterable[tuple[str, str]] | None,
        *,
        include_total: bool,
    ) -> PolicyListResponse:
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
                        model=Policy,
                        response_type=PolicyListResponse,
                        response_type_converter=PolicyRead.model_validate,
                        limit=1,
                        query_params_items=query_params_items,
                        include_total=True,
                    )
                    total = (db_count_resp.total or 0) + len(all_builtins)
                return PolicyListResponse(resources=page, next=nxt, total=total)
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

    async def list_policies(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> PolicyListResponse:
        """List policies with filtering and pagination."""
        excluded_params = {"limit", "cursor", "sort", "include_total"}
        query_params: dict[str, str] = {}
        if query_params_items:
            query_params = {k: v for k, v in query_params_items if k not in excluded_params}

        project_eligible = query_params.pop("project_eligible", None) == "true"
        scope_filter = "project" if project_eligible else None

        all_builtins = self._filter_builtin_policies(query_params, scope_filter=scope_filter)

        filtered_items: Iterable[tuple[str, str]] | None = query_params_items
        if query_params_items:
            filtered_items = [(k, v) for k, v in query_params_items if k not in ("project_eligible", "scope")]
            if project_eligible:
                filtered_items = [*filtered_items, ("scope", "project")]

        return await self._list_with_builtins(
            all_builtins,
            limit,
            cursor,
            sort,
            filtered_items,
            include_total=include_total,
        )

    async def list_project_policies(
        self,
        project_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> PolicyListResponse:
        """List policies visible within a project."""
        excluded_params = {"limit", "cursor", "sort", "include_total"}
        query_params: dict[str, str] = {}
        if query_params_items:
            query_params = {k: v for k, v in query_params_items if k not in excluded_params}

        all_builtins = self._filter_builtin_policies(query_params, scope_filter="project")
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

    async def update_policy(
        self,
        policy_id: UUID,
        name: str | None = None,
        description: str | None = None,
        statements: list[dict[str, Any]] | None = None,
        labels: dict[str, str] | None = None,
    ) -> Policy:
        """Update a policy. Builtin policies cannot be updated."""
        if self.get_policy_read(policy_id):
            msg = "Cannot modify builtin policy"
            raise BuiltinProtectionError(msg)

        policy = await self.get_policy(policy_id)
        if policy.is_builtin:
            msg = "Cannot modify builtin policy"
            raise BuiltinProtectionError(msg)

        if name is not None and name != policy.name:
            if is_builtin_policy(name):
                msg = f"Policy name '{name}' is reserved for a built-in policy"
                raise PolicyNameConflictError(msg)
            await self._check_name_conflict(name, policy.project_id)
            old_name = policy.name
            policy.name = name
            await self._propagate_policy_rename(old_name, name)
        if description is not None:
            policy.description = description
        if statements is not None:
            self._validate_no_deny_effect(statements)
            self._validate_resource_actions(statements)
            if policy.project_id is not None:
                self._validate_project_statements(statements)
            policy.statements = statements
        if labels is not None:
            policy.labels = labels

        self.session.add(policy)
        await self.session.commit()
        await self.session.refresh(policy)

        logger.info("Updated policy", policy_id=str(policy_id))
        AuditEventDispatcher.dispatch(
            PolicyLifecycleEvent(
                policy_id=policy.id,
                policy_name=policy.name,
                action="updated",
                project_id=policy.project_id,
            ),
        )
        return policy

    async def delete_policy(self, policy_id: UUID) -> None:
        """Delete a policy and remove it from any roles that reference it."""
        from syntara.authz.models.role import Role  # noqa: PLC0415

        if self.get_policy_read(policy_id):
            msg = "Cannot delete builtin policy"
            raise BuiltinProtectionError(msg)

        policy = await self.get_policy(policy_id)
        if policy.is_builtin:
            msg = "Cannot delete builtin policy"
            raise BuiltinProtectionError(msg)

        result = await self.session.exec(select(Role).where(Role.policy_names.contains([policy.name])))  # type: ignore[attr-defined]
        affected_roles = result.all()
        affected_count = len(affected_roles)
        for role in affected_roles:
            role.policy_names = [n for n in role.policy_names if n != policy.name]
            self.session.add(role)

        await self.session.delete(policy)
        await self.session.commit()

        logger.info("Deleted policy", policy_id=str(policy_id))
        AuditEventDispatcher.dispatch(
            PolicyLifecycleEvent(
                policy_id=policy.id,
                policy_name=policy.name,
                action="deleted",
                project_id=policy.project_id,
                affected_roles_count=affected_count,
            ),
        )

    async def _propagate_policy_rename(self, old_name: str, new_name: str) -> None:
        """Update all roles that reference the old policy name."""
        from syntara.authz.models.role import Role  # noqa: PLC0415

        result = await self.session.exec(select(Role).where(Role.policy_names.contains([old_name])))  # type: ignore[attr-defined]
        for role in result.all():
            role.policy_names = [new_name if n == old_name else n for n in role.policy_names]
            self.session.add(role)

    async def _check_name_conflict(self, name: str, project_id: UUID | None) -> None:
        """Check if a policy name already exists in the same scope."""
        query = select(Policy).where(Policy.name == name)
        if project_id is not None:
            query = query.where(Policy.project_id == project_id)
        else:
            query = query.where(Policy.project_id.is_(None))  # type: ignore[union-attr]
        result = await self.session.exec(query)
        if result.first():
            scope = f"project {project_id}" if project_id else "global scope"
            msg = f"Policy '{name}' already exists in {scope}"
            raise PolicyNameConflictError(msg)

    @staticmethod
    def _filter_builtin_policies(
        query_params: dict[str, str],
        scope_filter: str | None = None,
    ) -> list[PolicyRead]:
        """Return builtin policies matching query_params filters."""
        if query_params.get("is_builtin") == "false":
            return []

        effective_scope = scope_filter
        if not effective_scope and query_params.get("project_id"):
            effective_scope = "project"

        reads = []
        for p in BUILTIN_POLICIES:
            if effective_scope and p.scope != effective_scope:
                continue
            if not matches_query_param(p.scope, "scope", query_params):
                continue
            if not matches_query_param(p.name, "name", query_params):
                continue
            read = _builtin_policy_to_read(p.name)
            if read:
                reads.append(read)
        return reads
