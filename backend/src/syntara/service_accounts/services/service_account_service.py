"""Service account service layer for business logic."""

from collections.abc import Iterable
from uuid import UUID

import structlog
from sqlalchemy import delete as sa_delete
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.models.project import Project
from syntara.core.exceptions import assert_project_id_unchanged
from syntara.core.models import User
from syntara.core.services import BaseService
from syntara.core.services.extensions import ConvertResourceMixin
from syntara.service_accounts.exceptions import ServiceAccountNameConflictError, ServiceAccountNotFoundError
from syntara.service_accounts.models.service_account import ServiceAccount, ServiceAccountStatus
from syntara.service_accounts.models.service_account_credential import ServiceAccountCredential
from syntara.service_accounts.schemas import ServiceAccountListResponse, ServiceAccountRead
from syntara.settings.cache.settings_cache import get_runtime_settings

logger = structlog.stdlib.get_logger(__name__)


class ServiceAccountConvertMixin(ConvertResourceMixin):
    """Convert ServiceAccount model to ServiceAccountRead response."""

    def convert_resource(self, resource: ServiceAccount) -> ServiceAccountRead:  # type: ignore[override]
        """Convert ServiceAccount to read schema."""
        return ServiceAccountRead.model_validate(resource)


class ServiceAccountService(BaseService):
    """Service for service account business logic."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with database session and current user."""
        super().__init__(session, user, convert_resource_mixin=ServiceAccountConvertMixin())

    async def create_service_account(
        self,
        name: str,
        project_id: UUID,
        *,
        description: str | None = None,
    ) -> ServiceAccount:
        """Create a new service account.

        Args:
            name: Human-readable name.
            project_id: Project to create the service account in.
            description: Optional description.

        Returns:
            The created ServiceAccount.

        Raises:
            ServiceAccountNameConflictError: If name already exists in the project.

        """
        service_account = ServiceAccount(
            name=name,
            description=description,
            status=ServiceAccountStatus.ACTIVE,
            project_id=project_id,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        self.session.add(service_account)

        try:
            await self.session.flush()
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            error_str = str(e.orig) if e.orig else str(e)
            if "service_accounts" in error_str and "name" in error_str:
                raise ServiceAccountNameConflictError(name) from e
            raise

        logger.info(
            "Service account created",
            service_account_id=str(service_account.id),
            project_id=str(project_id),
        )

        return service_account

    async def to_read(self, service_account: ServiceAccount) -> ServiceAccountRead:
        """Convert a ServiceAccount to a read response (no secret)."""
        read = ServiceAccountRead.model_validate(service_account)
        project_info = await self._resolve_project_info(service_account.project_id)
        if project_info:
            read.project_name = project_info[0]
            read.is_project_deleted = project_info[1]
        return read

    async def _resolve_project_info(self, project_id: UUID) -> tuple[str, bool] | None:
        result = await self.session.exec(
            select(Project.name, Project.deleted_at).where(
                Project.id == project_id,
            )
        )
        row = result.first()
        if row is None:
            return None
        name, deleted_at = row
        return name, deleted_at is not None

    async def _resolve_project_infos(self, project_ids: set[UUID]) -> dict[UUID, tuple[str, bool]]:
        if not project_ids:
            return {}
        result = await self.session.exec(
            select(Project.id, Project.name, Project.deleted_at).where(
                Project.id.in_(project_ids),  # type: ignore[attr-defined]
            )
        )
        return {row_id: (name, deleted_at is not None) for row_id, name, deleted_at in result.all()}

    async def get_service_account(self, service_account_id: UUID) -> ServiceAccount:
        """Get a service account by ID.

        Raises:
            ServiceAccountNotFoundError: If not found.

        """
        query = select(ServiceAccount).where(
            ServiceAccount.id == service_account_id,
        )
        result = await self.session.exec(query)
        service_account = result.one_or_none()

        if service_account is None:
            msg = f"Service account {service_account_id} not found"
            raise ServiceAccountNotFoundError(msg)

        return service_account

    async def list_service_accounts(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> ServiceAccountListResponse:
        """List service accounts with filtering, sorting, and pagination."""
        response = await self.list_resources(
            model=ServiceAccount,
            response_type=ServiceAccountListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=query_params_items,
            include_total=include_total,
            allowed_projects=allowed_projects,
        )
        project_ids = {r.project_id for r in response.resources}
        project_infos = await self._resolve_project_infos(project_ids)
        for resource in response.resources:
            info = project_infos.get(resource.project_id)
            if info:
                resource.project_name = info[0]
                resource.is_project_deleted = info[1]
        response.max_lifetime_days = await get_runtime_settings().get_int(
            "service_accounts.credential_max_lifetime_days"
        )
        return response

    async def update_service_account(
        self,
        service_account_id: UUID,
        *,
        project_id: UUID | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> ServiceAccount:
        """Update a service account's name and/or description.

        Raises:
            ServiceAccountNotFoundError: If not found.
            ServiceAccountNameConflictError: If the new name conflicts.

        """
        service_account = await self.get_service_account(service_account_id)

        assert_project_id_unchanged(service_account.project_id, project_id)

        if name is not None:
            service_account.name = name
        if description is not None:
            service_account.description = description

        service_account.update_by_user(self.user.id)

        try:
            self.session.add(service_account)
            await self.session.flush()
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            if name is not None:
                raise ServiceAccountNameConflictError(name) from e
            raise

        await self.session.refresh(service_account)
        return service_account

    async def delete_service_account(self, service_account_id: UUID) -> None:
        """Hard-delete a service account and clean up linked resources.

        Deletes credentials, revokes non-builtin role assignments, then
        removes the service account row. The principals row is left intact
        to preserve created_by/updated_by FK integrity.

        Raises:
            ServiceAccountNotFoundError: If not found.

        """
        service_account = await self.get_service_account(service_account_id)
        sa_name = service_account.name

        # Delete all credentials for this SA
        await self.session.exec(
            sa_delete(ServiceAccountCredential).where(
                col(ServiceAccountCredential.service_account_id) == service_account_id
            )
        )

        # SAs never receive builtin assignments; filter is defensive
        await self.session.exec(
            sa_delete(RoleAssignment).where(
                col(RoleAssignment.principal_id) == service_account_id,
                col(RoleAssignment.is_builtin) == False,  # noqa: E712
            )
        )

        await self.session.delete(service_account)
        await self.session.commit()

        logger.info("Service account deleted", service_account_id=str(service_account_id), name=sa_name)

    async def disable_service_account(self, service_account_id: UUID) -> ServiceAccount:
        """Set a service account's status to disabled.

        Raises:
            ServiceAccountNotFoundError: If not found.

        """
        service_account = await self.get_service_account(service_account_id)

        # Core UPDATE bypasses before_flush — apply actor ContextVars first (AAP-83651).
        from syntara.core.database.session import apply_audit_context  # noqa: PLC0415

        await self.session.run_sync(apply_audit_context)
        await self.session.exec(
            update(ServiceAccount)
            .where(ServiceAccount.id == service_account_id)  # type: ignore[arg-type]
            .values(token_version=ServiceAccount.token_version + 1)
        )

        service_account.status = ServiceAccountStatus.DISABLED
        service_account.update_by_user(self.user.id)
        self.session.add(service_account)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(service_account)

        logger.info("Service account disabled", service_account_id=str(service_account_id))
        return service_account

    async def enable_service_account(self, service_account_id: UUID) -> ServiceAccount:
        """Set a service account's status to active.

        Raises:
            ServiceAccountNotFoundError: If not found.

        """
        service_account = await self.get_service_account(service_account_id)
        service_account.status = ServiceAccountStatus.ACTIVE
        service_account.update_by_user(self.user.id)

        self.session.add(service_account)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(service_account)

        logger.info("Service account enabled", service_account_id=str(service_account_id))
        return service_account
