"""Integration Service for database operations and business logic."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import UUID

import structlog
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.models.project import Project
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.queries.project_queries import assert_project_alive
from syntara.core.services import BaseService
from syntara.core.services.secret_service import SecretService
from syntara.credentials.exceptions import CredentialDisabledError
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.integrations.adapters.factory import create_health_check_adapter
from syntara.integrations.adapters.protocol import (
    DiscoveredLLMModel,
    DiscoveredTool,
    DiscoveredToolParameter,
    DiscoverResult,
    ValidateResult,
)
from syntara.integrations.audit import (
    IntegrationCreateEvent,
    IntegrationDeleteEvent,
    IntegrationDiscoverEvent,
    IntegrationRefreshEvent,
    IntegrationUpdateEvent,
    IntegrationValidateEvent,
)
from syntara.integrations.exceptions import (
    IntegrationCredentialRequiredError,
    IntegrationCredentialTypeMismatchError,
    IntegrationNameConflictError,
    IntegrationNotFoundError,
    IntegrationRefreshNotSupportedError,
    IntegrationScopeError,
)
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type, resolve_mcp_bearer_token
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationListResponse,
    IntegrationProjectAssignment,
    IntegrationProjectAssignmentListResponse,
    IntegrationProjectAssignmentRead,
    IntegrationRead,
    IntegrationRefreshStatus,
    IntegrationScope,
    IntegrationStatus,
    IntegrationSystemUpdate,
    IntegrationTestConnection,
    IntegrationType,
    IntegrationUpdate,
    RefreshResult,
)
from syntara.integrations.models.integration_configuration import IntegrationConfigurationInputTypes
from syntara.integrations.models.llm_model import LLMModel
from syntara.integrations.services.model_profile_lookup import lookup_model_profile
from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.tool_manager.models.tool import Tool, ToolParameter, ToolParameterType, ToolStatus

logger = structlog.stdlib.get_logger(__name__)

ALLOWED_CREDENTIAL_TYPES: dict[IntegrationType, frozenset[str]] = {
    IntegrationType.MCP_SERVER: frozenset({"HTTP Bearer Token"}),
    IntegrationType.LLM_PROVIDER: frozenset({"LLM Provider"}),
    IntegrationType.ANSIBLE_AUTOMATION_PLATFORM: frozenset({"Ansible Automation Platform"}),
}

CREDENTIAL_REQUIRED_TYPES: frozenset[IntegrationType] = frozenset(
    {
        IntegrationType.LLM_PROVIDER,
        IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
    }
)

_REFRESHABLE_TYPES: frozenset[IntegrationType] = frozenset(
    {
        IntegrationType.MCP_SERVER,
        IntegrationType.LLM_PROVIDER,
    }
)


class IntegrationService(BaseService):
    """Service for Integration CRUD operations."""

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        secret_service: SecretService | None = None,
    ) -> None:
        """Initialize with database session, current user, and optional secret service."""
        super().__init__(session, user)
        self._secret_service = secret_service

    def _is_duplicate_name_error(self, e: IntegrityError) -> bool:
        return "uq_integrations_name" in str(e)

    async def _handle_integrity_error(self, e: IntegrityError, integration_name: str) -> NoReturn:
        if self._is_duplicate_name_error(e):
            raise IntegrationNameConflictError(integration_name) from e
        raise e

    async def _raise_if_name_exists(self, name: str) -> None:
        """Raise IntegrationNameConflictError if an integration with this name already exists."""
        result = await self.session.exec(select(Integration).where(Integration.name == name).limit(1))
        if result.first() is not None:
            raise IntegrationNameConflictError(name)

    async def _validate_credential_type(
        self,
        integration_type: IntegrationType,
        credential_id: UUID,
    ) -> None:
        """Verify the credential's type is compatible with the integration type."""
        _, cred_type = await fetch_credential_with_type(self.session, credential_id, require_secret=False)

        allowed = ALLOWED_CREDENTIAL_TYPES.get(integration_type)
        if allowed and cred_type.name not in allowed:
            raise IntegrationCredentialTypeMismatchError(integration_type.value, cred_type.name, allowed)

    @staticmethod
    def _validate_discovered_resources(data: IntegrationCreate) -> None:
        """Reject discovered resources that don't match the integration type."""
        if data.discovered_tools and data.integration_type != IntegrationType.MCP_SERVER:
            msg = f"discovered_tools is not valid for {data.integration_type.value} integrations"
            raise ValueError(msg)
        if data.discovered_models and data.integration_type != IntegrationType.LLM_PROVIDER:
            msg = f"discovered_models is not valid for {data.integration_type.value} integrations"
            raise ValueError(msg)

    async def _sync_initial_resources(self, integration: Integration, data: IntegrationCreate) -> None:
        """Sync discovered tools or models provided at creation time."""
        if data.integration_type == IntegrationType.MCP_SERVER and data.discovered_tools:
            discovered = [
                DiscoveredTool(
                    name=t.name,
                    description=t.description,
                    parameters=[DiscoveredToolParameter.model_validate(p) for p in (t.parameters or [])]
                    if t.parameters
                    else None,
                )
                for t in data.discovered_tools
            ]
            enabled_map = {t.name: t.enabled for t in data.discovered_tools}
            synced, updated, missing = await self._sync_mcp_tools(integration, discovered, enabled_map=enabled_map)
            now = datetime.now(UTC)
            integration.refresh_status = IntegrationRefreshStatus.AVAILABLE
            integration.last_refreshed_at = now
            integration.last_successful_refresh_at = now
            await self.session.flush()
            logger.info(
                "Initial tool sync completed",
                integration_id=str(integration.id),
                synced=synced,
                updated=updated,
                missing=missing,
            )
        elif data.integration_type == IntegrationType.LLM_PROVIDER and data.discovered_models:
            discovered_models = [
                DiscoveredLLMModel(
                    id=m.model_id,
                    name=m.name,
                    description=m.description,
                )
                for m in data.discovered_models
            ]
            enabled_map = {m.model_id: m.enabled for m in data.discovered_models}
            default_model_id = next((m.model_id for m in data.discovered_models if m.is_default), None)
            synced, updated, missing = await self._sync_llm_models(
                integration, discovered_models, enabled_map=enabled_map, default_model_id=default_model_id
            )
            now = datetime.now(UTC)
            integration.refresh_status = IntegrationRefreshStatus.AVAILABLE
            integration.last_refreshed_at = now
            integration.last_successful_refresh_at = now
            await self.session.flush()
            logger.info(
                "Initial model sync completed",
                integration_id=str(integration.id),
                synced=synced,
                updated=updated,
                missing=missing,
            )

    async def _get_or_raise(self, integration_id: UUID, *, for_update: bool = False) -> Integration:
        query = select(Integration).filter(
            Integration.id == integration_id,  # type: ignore[arg-type]
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.exec(query)
        integration = result.one_or_none()

        if not integration:
            raise IntegrationNotFoundError(integration_id)

        return integration

    async def _to_read_with_counts(
        self,
        integration: Integration,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> IntegrationRead:
        """Convert an Integration ORM model to IntegrationRead with tool and model counts."""
        result = IntegrationRead.model_validate(integration)
        tool_counts = await self._get_tool_counts([integration.id])
        total, enabled = tool_counts.get(integration.id, (0, 0))
        result.total_tool_count = total
        result.enabled_tool_count = enabled
        model_counts = await self._get_model_counts([integration.id])
        m_total, m_enabled = model_counts.get(integration.id, (0, 0))
        result.total_model_count = m_total
        result.enabled_model_count = m_enabled
        project_ids_map = await self._get_assigned_project_ids([integration.id])
        result.project_ids = self._filter_project_ids(project_ids_map.get(integration.id, []), allowed_projects)
        await self._resolve_user_fields([result])
        return result

    @staticmethod
    def _filter_project_ids(project_ids: list[UUID], allowed_projects: AllowedProjectsResult | None) -> list[UUID]:
        if allowed_projects is None or allowed_projects.all_projects:
            return project_ids
        allowed_set = set(allowed_projects.project_ids)
        return [pid for pid in project_ids if pid in allowed_set]

    async def _get_tool_counts(self, integration_ids: list[UUID]) -> dict[UUID, tuple[int, int]]:
        """Fetch (total, enabled) tool counts per integration in a single query."""
        if not integration_ids:
            return {}
        query = (
            select(
                Tool.integration_id,
                func.count().label("total"),
                func.sum(case((col(Tool.enabled).is_(True), 1), else_=0)).label("enabled"),
            )
            .where(col(Tool.integration_id).in_(integration_ids))
            .group_by(col(Tool.integration_id))
        )
        rows = await self.session.execute(query)
        return {row.integration_id: (int(row.total), int(row.enabled or 0)) for row in rows.all()}

    async def _get_model_counts(self, integration_ids: list[UUID]) -> dict[UUID, tuple[int, int]]:
        """Fetch (total, enabled) LLM model counts per integration in a single query."""
        if not integration_ids:
            return {}
        query = (
            select(
                LLMModel.integration_id,
                func.count().label("total"),
                func.sum(case((col(LLMModel.enabled).is_(True), 1), else_=0)).label("enabled"),
            )
            .where(col(LLMModel.integration_id).in_(integration_ids))
            .group_by(col(LLMModel.integration_id))
        )
        rows = await self.session.execute(query)
        return {row.integration_id: (int(row.total), int(row.enabled or 0)) for row in rows.all()}

    async def _get_assigned_project_ids(self, integration_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        """Batch-fetch assigned project IDs per integration."""
        if not integration_ids:
            return {}
        query = select(
            IntegrationProjectAssignment.integration_id,
            IntegrationProjectAssignment.project_id,
        ).where(col(IntegrationProjectAssignment.integration_id).in_(integration_ids))
        rows = await self.session.execute(query)
        result: dict[UUID, list[UUID]] = {}
        for row in rows.all():
            result.setdefault(row.integration_id, []).append(row.project_id)
        return result

    async def assign_project(self, integration_id: UUID, project_id: UUID) -> IntegrationProjectAssignmentRead:
        """Assign a project to a project-scoped integration."""
        integration = await self._get_or_raise(integration_id)
        if integration.scope != IntegrationScope.PROJECT:
            raise IntegrationScopeError(
                integration_id,
                f"Cannot assign projects to a {integration.scope.value}-scoped integration",
            )
        await assert_project_alive(self.session, project_id)
        project = await self.session.get(Project, project_id)

        existing = (
            await self.session.exec(
                select(IntegrationProjectAssignment).where(
                    IntegrationProjectAssignment.integration_id == integration_id,
                    IntegrationProjectAssignment.project_id == project_id,
                )
            )
        ).one_or_none()

        if existing is None:
            existing = IntegrationProjectAssignment(
                integration_id=integration_id,
                project_id=project_id,
            )
            self.session.add(existing)
            await self.session.flush()

        await self.session.commit()
        return IntegrationProjectAssignmentRead(
            project_id=project_id,
            project_name=project.name if project else str(project_id),
            created_at=existing.created_at,
        )

    async def unassign_project(self, integration_id: UUID, project_id: UUID) -> None:
        """Remove a project assignment from an integration."""
        integration = await self._get_or_raise(integration_id)
        if integration.scope != IntegrationScope.PROJECT:
            raise IntegrationScopeError(
                integration_id,
                f"Cannot unassign projects from a {integration.scope.value}-scoped integration",
            )
        stmt = delete(IntegrationProjectAssignment).where(
            IntegrationProjectAssignment.integration_id == integration_id,  # type: ignore[arg-type]
            IntegrationProjectAssignment.project_id == project_id,  # type: ignore[arg-type]
        )
        await self.session.exec(stmt)
        await self.session.commit()

    async def list_assigned_projects(
        self,
        integration_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> IntegrationProjectAssignmentListResponse:
        """List project assignments for an integration with pagination."""
        await self._get_or_raise(integration_id)

        id_restriction: list[UUID] | None = None
        if allowed_projects is not None and not allowed_projects.all_projects:
            rows = await self.session.execute(
                select(IntegrationProjectAssignment.id).where(
                    IntegrationProjectAssignment.integration_id == integration_id,
                    col(IntegrationProjectAssignment.project_id).in_(allowed_projects.project_ids),
                )
            )
            id_restriction = [row[0] for row in rows.all()]

        project_names: dict[UUID, str] = {}

        async def _fetch_project_names(assignments: list[IntegrationProjectAssignment]) -> None:
            if not assignments:
                return
            pids = [a.project_id for a in assignments]
            rows = await self.session.execute(select(Project.id, Project.name).where(col(Project.id).in_(pids)))
            project_names.update(dict(rows.all()))  # type: ignore[arg-type]

        def _to_read(assignment: IntegrationProjectAssignment) -> IntegrationProjectAssignmentRead:
            return IntegrationProjectAssignmentRead(
                project_id=assignment.project_id,
                project_name=project_names.get(assignment.project_id, str(assignment.project_id)),
                created_at=assignment.created_at,
            )

        return await self.list_resources(
            model=IntegrationProjectAssignment,  # type: ignore[type-var]
            response_type=IntegrationProjectAssignmentListResponse,
            response_type_converter=_to_read,
            post_query_callback=_fetch_project_names,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=[("integration_id", str(integration_id))],
            id_restriction=id_restriction,
            include_total=include_total,
        )

    def _validate_configuration_ssrf(self, configuration: IntegrationConfigurationInputTypes) -> None:
        """Reject a base_url that resolves to a private, reserved, or cloud metadata address.

        Called at write time (create/patch) and again in this service's outbound
        entrypoints (discover/validate/refresh) as defense in depth against DNS re-pointing.
        The same policy is re-run at the runtime outbound boundaries that read the stored
        base_url directly (AAP proxy, workflow AAP resolution, LLM invocation, MCP tool
        connect); all boundaries route through the shared
        :func:`validate_integration_configuration_no_ssrf` choke point so the policy cannot
        drift. Loopback and other private hosts are rejected unless allowlisted via
        integration_url_allowed_hosts. The DNS-resolving SSRF check cannot live in the
        configuration model validators because those also run when configurations are
        deserialized from the database on every read.
        """
        try:
            validate_integration_configuration_no_ssrf(configuration)
        except ValueError as e:
            msg = "base_url must not resolve to a private, reserved, or cloud metadata address."
            raise SafeValueError(msg) from e

    async def create_integration(self, data: IntegrationCreate) -> IntegrationRead:
        """Create a new integration.

        If ``discovered_tools`` is provided, Tool records are created
        immediately with the user's enabled/disabled selections.
        If ``discovered_models`` is provided, LLMModel records are created
        immediately with the user's enabled/disabled/default selections.
        Otherwise, tools or models are created on first refresh via
        ``POST /integrations/{id}/refresh``.
        """
        if data.management_credential_id is not None:
            await self._validate_credential_type(data.integration_type, data.management_credential_id)
        elif data.integration_type in CREDENTIAL_REQUIRED_TYPES:
            raise IntegrationCredentialRequiredError(data.integration_type.value)

        self._validate_configuration_ssrf(data.configuration)

        integration = Integration(
            name=data.name,
            description=data.description,
            integration_type=data.integration_type,
            configuration=data.configuration,
            management_credential_id=data.management_credential_id,
            enabled=data.enabled,
            scope=data.scope,
            labels=data.labels,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        self.session.add(integration)

        try:
            await self.session.flush()
        except IntegrityError as e:
            AuditEventDispatcher.dispatch(
                IntegrationCreateEvent(
                    integration_id=integration.id,
                    integration_name=data.name,
                    integration_type=data.integration_type.value,
                    description=data.description,
                    error_type=type(e).__name__,
                )
            )
            await self._handle_integrity_error(e, data.name)

        self._validate_discovered_resources(data)
        await self._sync_initial_resources(integration, data)

        await self.session.commit()

        result = await self._to_read_with_counts(integration)
        AuditEventDispatcher.dispatch(
            IntegrationCreateEvent(
                integration_id=integration.id,
                integration_name=integration.name,
                integration_type=integration.integration_type.value,
                description=integration.description,
                initial_status=integration.validation_status,
            )
        )
        return result

    async def get_integration(
        self,
        integration_id: UUID,
        *,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> IntegrationRead:
        """Get an integration by ID, optionally enforcing project-scoped visibility."""
        integration = await self._get_or_raise(integration_id)
        if allowed_projects is not None:
            await self._enforce_visibility(integration, allowed_projects)
        return await self._to_read_with_counts(integration, allowed_projects=allowed_projects)

    async def _enforce_visibility(self, integration: Integration, allowed_projects: AllowedProjectsResult) -> None:
        """Raise IntegrationNotFoundError if the integration is not visible to the caller."""
        if allowed_projects.all_projects:
            return
        visible_ids = await self.resolve_visible_integration_ids(self.session, allowed_projects)
        if visible_ids is not None and integration.id not in set(visible_ids):
            raise IntegrationNotFoundError(integration.id)

    async def list_integrations(
        self,
        limit: int = 100,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult,
        project_id: UUID | None = None,
    ) -> IntegrationListResponse:
        """List integrations with filtering, sorting, and pagination.

        Scope visibility rules:
        - GLOBAL integrations are visible to all callers with integration:read.
        - PROJECT integrations are visible only when the caller has access to at least one
          of the projects the integration is assigned to.
        - When project_id is provided, results are further restricted to integrations that
          are global or assigned to that specific project. The user must have RBAC access
          to the project; querying an inaccessible project returns only globals.
        """
        id_restriction: list[UUID] | None = None
        id_restriction = await self.resolve_visible_integration_ids(self.session, allowed_projects)

        if project_id is not None:
            user_has_project_access = allowed_projects.all_projects or project_id in allowed_projects.project_ids
            project_scoped_ids = await self._resolve_project_scoped_ids(
                project_id, include_assignments=user_has_project_access
            )
            id_restriction = self._intersect_id_restrictions(id_restriction, project_scoped_ids)

        filtered_params = [(k, v) for k, v in query_params_items if k != "project_id"] if query_params_items else None

        response = await self.list_resources(
            model=Integration,
            response_type=IntegrationListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=filtered_params,
            include_total=include_total,
            id_restriction=id_restriction,
        )

        integration_ids = [r.id for r in response.resources if r.id]
        tool_counts = await self._get_tool_counts(integration_ids)
        model_counts = await self._get_model_counts(integration_ids)
        project_ids_map = await self._get_assigned_project_ids(integration_ids)
        for resource in response.resources:
            t_total, t_enabled = tool_counts.get(resource.id, (0, 0))
            resource.total_tool_count = t_total
            resource.enabled_tool_count = t_enabled
            m_total, m_enabled = model_counts.get(resource.id, (0, 0))
            resource.total_model_count = m_total
            resource.enabled_model_count = m_enabled
            resource.project_ids = self._filter_project_ids(project_ids_map.get(resource.id, []), allowed_projects)

        await self._resolve_user_fields(response.resources)

        return response

    @staticmethod
    async def resolve_visible_integration_ids(
        session: AsyncSession, allowed_projects: AllowedProjectsResult
    ) -> list[UUID] | None:
        """Return the set of integration IDs visible to the caller, or None for unrestricted access."""
        if allowed_projects.all_projects:
            return None

        global_query = select(Integration.id).where(
            Integration.scope == IntegrationScope.GLOBAL,
        )

        if not allowed_projects.project_ids:
            result = await session.execute(global_query)
            return list(result.scalars().all())

        assignment_query = select(IntegrationProjectAssignment.integration_id).where(
            col(IntegrationProjectAssignment.project_id).in_(allowed_projects.project_ids),
        )

        union_result = await session.execute(global_query.union(assignment_query))
        return list(union_result.scalars().all())

    async def _resolve_project_scoped_ids(self, project_id: UUID, *, include_assignments: bool = True) -> list[UUID]:
        """Return integration IDs that are global or assigned to a specific project.

        When include_assignments is False (caller lacks access to the project),
        only global integrations are returned.
        """
        global_query = select(Integration.id).where(
            Integration.scope == IntegrationScope.GLOBAL,
        )
        if not include_assignments:
            result = await self.session.execute(global_query)
            return list(result.scalars().all())
        assignment_query = select(IntegrationProjectAssignment.integration_id).where(
            IntegrationProjectAssignment.project_id == project_id,
        )
        result = await self.session.execute(global_query.union(assignment_query))
        return list(result.scalars().all())

    @staticmethod
    def _intersect_id_restrictions(
        rbac_ids: list[UUID] | None,
        project_ids: list[UUID],
    ) -> list[UUID]:
        """Intersect RBAC visibility with project-scoped IDs."""
        if rbac_ids is None:
            return project_ids
        return list(set(rbac_ids) & set(project_ids))

    async def _validate_patch(self, integration: Integration, data: IntegrationUpdate) -> None:
        """Validate a patch payload against the existing integration before applying updates."""
        if data.configuration is not None:
            if data.configuration.integration_type != integration.integration_type.value:
                msg = (
                    f"configuration.integration_type '{data.configuration.integration_type}' "
                    f"does not match integration type '{integration.integration_type.value}'"
                )
                raise SafeValueError(msg)
            self._validate_configuration_ssrf(data.configuration)

        if "management_credential_id" in data.model_fields_set:
            if data.management_credential_id is not None:
                await self._validate_credential_type(integration.integration_type, data.management_credential_id)
            elif integration.integration_type in CREDENTIAL_REQUIRED_TYPES:
                raise IntegrationCredentialRequiredError(integration.integration_type.value)

        if data.name is not None and data.name != integration.name:
            await self._raise_if_name_exists(data.name)

    async def update_integration(self, integration_id: UUID, data: IntegrationUpdate) -> IntegrationRead:
        """Apply partial updates to an integration."""
        try:
            integration = await self._get_or_raise(integration_id)
        except IntegrationNotFoundError:
            AuditEventDispatcher.dispatch(
                IntegrationUpdateEvent(
                    integration_id=integration_id,
                    integration_name=str(integration_id),
                    error_type="IntegrationNotFoundError",
                )
            )
            raise

        await self._validate_patch(integration, data)

        if data.scope == IntegrationScope.GLOBAL and integration.scope == IntegrationScope.PROJECT:
            stmt = delete(IntegrationProjectAssignment).where(
                IntegrationProjectAssignment.integration_id == integration_id,  # type: ignore[arg-type]
            )
            await self.session.exec(stmt)

        integration_name = data.name if data.name is not None else integration.name
        updated_fields = list(data.model_fields_set)

        for field in data.model_fields_set:
            setattr(integration, field, getattr(data, field))

        integration.updated_by = self.user.id
        integration.updated_at = datetime.now(UTC)

        try:
            await self.session.flush()
        except IntegrityError as e:
            AuditEventDispatcher.dispatch(
                IntegrationUpdateEvent(
                    integration_id=integration.id,
                    integration_name=integration_name,
                    updated_fields=updated_fields,
                    integration_type=integration.integration_type.value,
                    error_type=type(e).__name__,
                )
            )
            await self._handle_integrity_error(e, integration_name)

        await self.session.commit()

        result = await self._to_read_with_counts(integration)
        AuditEventDispatcher.dispatch(
            IntegrationUpdateEvent(
                integration_id=integration.id,
                integration_name=integration.name,
                updated_fields=updated_fields,
                integration_type=integration.integration_type.value,
            )
        )
        return result

    async def update_validation_status(self, integration_id: UUID, data: IntegrationSystemUpdate) -> IntegrationRead:
        """Apply system-managed validation status updates."""
        integration = await self._get_or_raise(integration_id)

        for field in data.model_fields_set:
            setattr(integration, field, getattr(data, field))

        integration.last_validated_at = datetime.now(UTC)

        await self.session.flush()
        return await self._to_read_with_counts(integration)

    async def _resolve_credential(self, credential_id: UUID) -> dict[str, object]:
        """Resolve a credential to its extra_vars dict for adapter use.

        Fetches the credential, verifies it is enabled, decrypts its secret,
        and applies injector mappings to produce the resolved variable dict.

        Raises:
            IntegrationCredentialNotFoundError: If the credential or its type is not found.
            CredentialDisabledError: If the credential is disabled.
            RuntimeError: If SecretService is not available.

        """
        if self._secret_service is None:
            msg = "SecretService is required for credential resolution"
            raise RuntimeError(msg)

        credential, cred_type = await fetch_credential_with_type(self.session, credential_id)
        if not credential.enabled:
            raise CredentialDisabledError(credential.name)
        logger.debug("Resolving credential", credential_id=str(credential_id), credential_type=cred_type.name)
        # fetch_credential_with_type raises if secret_id is None
        decrypted_inputs = await self._secret_service.retrieve_secret(credential.secret_id)  # type: ignore[arg-type]
        resolved = InjectorResolver.resolve(cred_type.injectors or {}, decrypted_inputs)
        return resolved.extra_vars

    async def _fail_validation(self, integration: Integration, error: Exception) -> NoReturn:
        """Persist ERROR validation state, dispatch audit event, and re-raise."""
        integration.validation_status = IntegrationStatus.ERROR
        integration.validation_error = str(error)
        integration.last_validated_at = datetime.now(UTC)
        await self.session.commit()
        AuditEventDispatcher.dispatch(
            IntegrationValidateEvent(
                integration_id=integration.id,
                integration_name=integration.name,
                integration_type=integration.integration_type.value,
                result_status=IntegrationStatus.ERROR,
                error_type=type(error).__name__,
                error_message=str(error),
            )
        )
        raise error

    async def _fail_refresh(self, integration: Integration, error: Exception) -> NoReturn:
        """Persist ERROR refresh state, dispatch audit event, and re-raise."""
        integration.refresh_status = IntegrationRefreshStatus.ERROR
        integration.refresh_error = str(error)
        integration.last_refreshed_at = datetime.now(UTC)
        await self.session.commit()
        AuditEventDispatcher.dispatch(
            IntegrationRefreshEvent(
                integration_id=integration.id,
                integration_name=integration.name,
                integration_type=integration.integration_type.value,
                result_status=IntegrationRefreshStatus.ERROR,
                error_type=type(error).__name__,
            )
        )
        raise error

    async def _handle_failed_discover(self, integration_id: UUID, discover_result: DiscoverResult) -> RefreshResult:
        """Persist ERROR state when adapter discovery reports failure."""
        integration = await self._get_or_raise(integration_id, for_update=True)
        integration.refresh_status = IntegrationRefreshStatus.ERROR
        integration.refresh_error = discover_result.error
        integration.last_refreshed_at = datetime.now(UTC)
        await self.session.commit()
        AuditEventDispatcher.dispatch(
            IntegrationRefreshEvent(
                integration_id=integration.id,
                integration_name=integration.name,
                integration_type=integration.integration_type.value,
                result_status=IntegrationRefreshStatus.ERROR,
                error_type=discover_result.error_type.value if discover_result.error_type else "DiscoverFailed",
            )
        )
        return RefreshResult(
            synced_count=0,
            updated_count=0,
            missing_count=0,
            refreshed_at=integration.last_refreshed_at or datetime.now(UTC),
        )

    async def _sync_discovered_resources(
        self, integration: Integration, integration_id: UUID, discover_result: DiscoverResult
    ) -> tuple[int, int, int]:
        """Dispatch to type-specific sync (MCP tools or LLM models)."""
        if integration.integration_type == IntegrationType.MCP_SERVER:
            return await self._sync_mcp_tools(integration, discover_result.discovered_tools or [])
        if integration.integration_type == IntegrationType.LLM_PROVIDER:
            return await self._sync_llm_models(integration, discover_result.discovered_models or [])
        raise IntegrationRefreshNotSupportedError(integration_id, integration.integration_type.value)

    async def _persist_refresh_error(self, integration_id: UUID, exc: Exception) -> None:
        """Log and persist ERROR state for unexpected refresh failures."""
        logger.exception(
            "Unexpected error during integration refresh",
            integration_id=str(integration_id),
            error_type=type(exc).__name__,
        )
        integration = await self._get_or_raise(integration_id, for_update=True)
        integration.refresh_status = IntegrationRefreshStatus.ERROR
        integration.refresh_error = f"Unexpected error during refresh: {type(exc).__name__}"
        integration.last_refreshed_at = datetime.now(UTC)
        await self.session.commit()

    async def validate_integration(self, integration_id: UUID) -> ValidateResult:
        """Run a lightweight connectivity ping on a saved integration.

        Resolves the management credential, dispatches to the type-specific
        adapter's validate() method, persists the result, and returns it.

        Status transitions: current → VALIDATING → AVAILABLE or ERROR.
        If the required management credential is missing, transitions
        directly to ERROR without reaching the adapter.
        ``last_validated_at`` is set after the check completes or on
        early failure to prevent the health-check worker from
        re-selecting the same integration every cycle.
        No tool sync is performed — use refresh_resources() for that.
        """
        logger.info("Starting integration validation", integration_id=str(integration_id))
        try:
            integration = await self._get_or_raise(integration_id)
        except IntegrationNotFoundError:
            AuditEventDispatcher.dispatch(
                IntegrationValidateEvent(
                    integration_id=integration_id,
                    integration_name=str(integration_id),
                    integration_type="unknown",
                    error_type="IntegrationNotFoundError",
                )
            )
            raise

        if integration.management_credential_id is None and integration.integration_type in CREDENTIAL_REQUIRED_TYPES:
            await self._fail_validation(
                integration, IntegrationCredentialRequiredError(integration.integration_type.value)
            )

        resolved_credential: dict[str, object] = {}
        if integration.management_credential_id:
            try:
                resolved_credential = await self._resolve_credential(integration.management_credential_id)
            except CredentialDisabledError as exc:
                await self._fail_validation(integration, exc)

        integration.validation_status = IntegrationStatus.VALIDATING
        integration.validation_error = None
        await self.session.commit()

        timeout_seconds: int = await get_runtime_settings().get("integrations.connection_test_timeout_seconds")
        # Re-check at call time (defense in depth): the stored base_url passed the write-time
        # check, but DNS could have been re-pointed to a private/metadata target since.
        self._validate_configuration_ssrf(integration.configuration)
        adapter = create_health_check_adapter(integration.integration_type, integration.configuration)

        try:
            result = await adapter.validate(resolved_credential, timeout_seconds)

            integration = await self._get_or_raise(integration_id, for_update=True)
            integration.validation_status = IntegrationStatus.AVAILABLE if result.success else IntegrationStatus.ERROR
            integration.validation_error = result.error
            integration.last_validated_at = datetime.now(UTC)
            await self.session.commit()
            logger.info(
                "Integration validation completed",
                integration_id=str(integration_id),
                success=result.success,
                status=integration.validation_status,
            )
        except Exception as exc:
            logger.exception(
                "Unexpected error during integration validation",
                integration_id=str(integration_id),
                error_type=type(exc).__name__,
            )
            integration = await self._get_or_raise(integration_id, for_update=True)
            integration.validation_status = IntegrationStatus.ERROR
            integration.validation_error = f"Unexpected error during validation: {type(exc).__name__}"
            integration.last_validated_at = datetime.now(UTC)
            await self.session.commit()
            raise

        AuditEventDispatcher.dispatch(
            IntegrationValidateEvent(
                integration_id=integration.id,
                integration_name=integration.name,
                integration_type=integration.integration_type.value,
                result_status=integration.validation_status,
                error_type=None if result.success else "HealthCheckFailed",
                error_message=result.error,
            )
        )

        return result

    async def discover(self, data: IntegrationTestConnection) -> DiscoverResult:
        """Test a connection for an unsaved integration and discover its resources.

        Resolves the credential, creates an adapter from the provided
        configuration, and runs discover(). No database writes.
        """
        # Reject SSRF-prone base_url before any outbound request. discover() bypasses
        # create/patch, so without this the adapter would hit private/metadata targets.
        self._validate_configuration_ssrf(data.configuration)

        if data.credential_id is None and data.integration_type in CREDENTIAL_REQUIRED_TYPES:
            raise IntegrationCredentialRequiredError(data.integration_type.value)

        resolved_credential: dict[str, object] = {}
        if data.credential_id is not None:
            resolved_credential = await self._resolve_credential(data.credential_id)

        timeout_seconds: int = await get_runtime_settings().get("integrations.connection_test_timeout_seconds")

        adapter = create_health_check_adapter(data.integration_type, data.configuration)
        result = await adapter.discover(resolved_credential, timeout_seconds)

        AuditEventDispatcher.dispatch(
            IntegrationDiscoverEvent(
                integration_type=data.integration_type.value,
                tools_found_count=len(result.discovered_tools or []),
                models_found_count=len(result.discovered_models or []),
                error_type=None
                if result.success
                else (result.error_type.value if result.error_type else "DiscoverFailed"),
            )
        )

        return result

    _RECENT_REFRESH_SECONDS = 60

    @staticmethod
    def _skip_if_recently_refreshed(integration: Integration, threshold_seconds: int) -> RefreshResult | None:
        """Return a no-op RefreshResult if refreshed within *threshold_seconds*, else None."""
        if integration.last_refreshed_at and (datetime.now(UTC) - integration.last_refreshed_at) < timedelta(
            seconds=threshold_seconds
        ):
            logger.info(
                "Skipping refresh; recently refreshed",
                integration_id=str(integration.id),
                last_refreshed_at=integration.last_refreshed_at.isoformat(),
            )
            return RefreshResult(
                synced_count=0,
                updated_count=0,
                missing_count=0,
                refreshed_at=integration.last_refreshed_at,
            )
        return None

    async def refresh_resources(self, integration_id: UUID, *, skip_if_recent: bool = False) -> RefreshResult:
        """Discover and sync resources (tools/models) for a saved integration.

        For MCP servers: discovers tools and upserts Tool records.
        For LLM providers: discovers models and upserts LLMModel records.
        Updates refresh_status and last_refreshed_at on the integration.

        When *skip_if_recent* is True (used by the periodic discovery worker),
        the refresh is skipped if the integration was already refreshed within
        the last 60 seconds, preventing redundant work when a manual refresh
        and a scheduled run overlap.

        Raises IntegrationRefreshNotSupportedError for unsupported integration types.
        """
        logger.info("Starting integration refresh", integration_id=str(integration_id))
        integration = await self._get_or_raise(integration_id)

        if skip_if_recent and (skipped := self._skip_if_recently_refreshed(integration, self._RECENT_REFRESH_SECONDS)):
            return skipped

        if integration.integration_type not in _REFRESHABLE_TYPES:
            raise IntegrationRefreshNotSupportedError(integration_id, integration.integration_type.value)

        if integration.management_credential_id is None and integration.integration_type in CREDENTIAL_REQUIRED_TYPES:
            await self._fail_refresh(
                integration, IntegrationCredentialRequiredError(integration.integration_type.value)
            )

        resolved_credential: dict[str, object] = {}
        if integration.management_credential_id:
            try:
                resolved_credential = await self._resolve_credential(integration.management_credential_id)
            except CredentialDisabledError as exc:
                await self._fail_refresh(integration, exc)

        integration.refresh_status = IntegrationRefreshStatus.REFRESHING
        integration.refresh_error = None
        await self.session.commit()

        timeout_seconds: int = await get_runtime_settings().get("integrations.connection_test_timeout_seconds")
        # Re-check at call time (defense in depth): the stored base_url passed the write-time
        # check, but DNS could have been re-pointed to a private/metadata target since.
        self._validate_configuration_ssrf(integration.configuration)
        adapter = create_health_check_adapter(integration.integration_type, integration.configuration)

        synced = updated = missing = 0
        try:
            discover_result = await adapter.discover(resolved_credential, timeout_seconds)

            if not discover_result.success:
                return await self._handle_failed_discover(integration_id, discover_result)

            synced, updated, missing = await self._sync_discovered_resources(
                integration, integration_id, discover_result
            )

            integration = await self._get_or_raise(integration_id, for_update=True)
            now = datetime.now(UTC)
            integration.last_refreshed_at = now
            integration.last_successful_refresh_at = now
            warning = await self._default_model_missing(integration, discover_result.discovered_models or [])
            integration.refresh_status = (
                IntegrationRefreshStatus.WARNING if warning else IntegrationRefreshStatus.AVAILABLE
            )
            integration.refresh_error = warning
            await self.session.commit()
            logger.info(
                "Integration refresh completed",
                integration_id=str(integration_id),
                synced=synced,
                updated=updated,
                missing=missing,
            )
        except Exception as exc:
            await self._persist_refresh_error(integration_id, exc)
            raise

        AuditEventDispatcher.dispatch(
            IntegrationRefreshEvent(
                integration_id=integration.id,
                integration_name=integration.name,
                integration_type=integration.integration_type.value,
                result_status=integration.refresh_status,
                synced_count=synced,
                updated_count=updated,
                missing_count=missing,
            )
        )

        return RefreshResult(
            synced_count=synced,
            updated_count=updated,
            missing_count=missing,
            refreshed_at=integration.last_refreshed_at,
        )

    async def _resolve_integration_credential(self, integration: Integration) -> str | None:
        """Decrypt and resolve the bearer token for an integration's management credential.

        Call only immediately before an outbound external connection. The returned
        value is used in the caller's local scope and never stored on self.

        Returns None if no credential is configured (unauthenticated integration).
        Raises if a credential is configured but cannot be resolved.
        """
        if not integration.management_credential_id:
            return None

        if self._secret_service is None:
            raise IntegrationCredentialRequiredError(integration.integration_type.value)

        return await resolve_mcp_bearer_token(self.session, self._secret_service, integration.id)

    async def _default_model_missing(
        self, integration: Integration, discovered_models: list[DiscoveredLLMModel]
    ) -> str | None:
        """Warning message if the integration's default LLM model was not in the latest discovery."""
        if integration.integration_type != IntegrationType.LLM_PROVIDER:
            return None
        default_model = (
            await self.session.exec(
                select(LLMModel).where(
                    LLMModel.integration_id == integration.id,
                    col(LLMModel.is_default).is_(True),
                )
            )
        ).first()
        discovered_ids = {m.id for m in discovered_models}
        if default_model is not None and default_model.model_id not in discovered_ids:
            return f"Default model '{default_model.model_id}' is no longer offered by the provider"
        return None

    async def _sync_mcp_tools(
        self,
        integration: Integration,
        discovered_tools: list[DiscoveredTool],
        *,
        enabled_map: dict[str, bool] | None = None,
    ) -> tuple[int, int, int]:
        """Upsert Tool records from a pre-fetched list of DiscoveredTool objects.

        Accepts the tool list produced by adapter.discover() so no additional
        MCP connection is made here — this is pure DB upsert logic.

        If ``enabled_map`` is provided, each tool's enabled state is set
        according to the map (used during creation with user selections).
        Otherwise all new tools default to enabled=True.

        Tools no longer present in the discovered list keep their admin
        enabled state unchanged and are marked MISSING, so workflow
        references stay valid and the orchestrator can still try them.

        Returns a (synced_count, updated_count, missing_count) tuple.
        The caller is responsible for committing the session.
        """
        existing_query = await self.session.exec(select(Tool).where(Tool.integration_id == integration.id))
        existing_tools = {t.name: t for t in existing_query.all()}
        found_names: set[str] = set()
        synced_count = 0
        updated_count = 0

        # Batch-delete all existing parameters for this integration's tools in one query
        existing_tool_ids = [t.id for t in existing_tools.values()]
        if existing_tool_ids:
            await self.session.exec(delete(ToolParameter).where(col(ToolParameter.tool_id).in_(existing_tool_ids)))

        # Collect new parameters to batch-add after the loop
        pending_params: list[tuple[Tool, list[ToolParameter]]] = []

        for tool_meta in discovered_tools:
            found_names.add(tool_meta.name)
            namespaced = f"{integration.name}::{tool_meta.name}"
            logger.debug(
                "Processing discovered tool",
                integration_id=str(integration.id),
                tool_name=tool_meta.name,
                is_existing=tool_meta.name in existing_tools,
            )
            parameters = _discovered_params_to_tool_params(tool_meta.parameters or [])

            if tool_meta.name in existing_tools:
                existing = existing_tools[tool_meta.name]
                existing.namespaced_name = namespaced
                existing.description = tool_meta.description
                existing.status = ToolStatus.AVAILABLE
                existing.last_refreshed_at = datetime.now(UTC)
                existing.refresh_error = None
                existing.updated_by = self.user.id
                existing.updated_at = datetime.now(UTC)
                pending_params.append((existing, parameters))
                updated_count += 1
            else:
                tool_enabled = enabled_map.get(tool_meta.name, True) if enabled_map else True
                new_tool = Tool(
                    integration_id=integration.id,
                    name=tool_meta.name,
                    namespaced_name=namespaced,
                    description=tool_meta.description,
                    enabled=tool_enabled,
                    last_refreshed_at=datetime.now(UTC),
                    created_by=self.user.id,
                    updated_by=self.user.id,
                )
                self.session.add(new_tool)
                pending_params.append((new_tool, parameters))
                synced_count += 1

        # Flush to assign IDs to new tools before adding parameters
        await self.session.flush()

        # Batch-insert all new parameters
        now = datetime.now(UTC)
        for tool, parameters in pending_params:
            for param in parameters:
                self.session.add(
                    ToolParameter(
                        tool_id=tool.id,
                        name=param.name,
                        type=param.type,
                        description=param.description or "",
                        required=bool(getattr(param, "required", False)),
                        created_at=now,
                        updated_at=now,
                    )
                )

        missing_count = 0
        for name, tool in existing_tools.items():
            if name not in found_names:
                logger.debug(
                    "Marking tool MISSING; no longer in discovered list",
                    integration_id=str(integration.id),
                    tool_name=name,
                )
                tool.status = ToolStatus.MISSING
                tool.updated_by = self.user.id
                tool.updated_at = datetime.now(UTC)
                missing_count += 1

        return synced_count, updated_count, missing_count

    async def delete_integration(self, integration_id: UUID) -> None:
        """Hard-delete an integration and all linked resources."""
        try:
            integration = await self._get_or_raise(integration_id)
        except IntegrationNotFoundError:
            AuditEventDispatcher.dispatch(
                IntegrationDeleteEvent(
                    integration_id=integration_id,
                    integration_name=str(integration_id),
                    error_type="IntegrationNotFoundError",
                )
            )
            raise

        integration_name = integration.name
        tools_count = await self._count_linked_tools(integration_id)

        await self._hard_delete_linked_tool_params(integration_id)
        await self._hard_delete_linked_tools(integration_id)
        await self._hard_delete_linked_models(integration_id)

        await self.session.exec(
            delete(IntegrationProjectAssignment).where(
                IntegrationProjectAssignment.integration_id == integration_id,  # type: ignore[arg-type]
            )
        )

        await self.session.delete(integration)
        await self.session.flush()
        await self.session.commit()

        AuditEventDispatcher.dispatch(
            IntegrationDeleteEvent(
                integration_id=integration_id,
                integration_name=integration_name,
                tools_deleted=tools_count,
            )
        )

    async def _count_linked_tools(self, integration_id: UUID) -> int:
        """Count Tool records owned by this integration."""
        count = await self.session.scalar(
            select(func.count()).select_from(Tool).where(Tool.integration_id == integration_id)
        )
        return count or 0

    async def _hard_delete_linked_tool_params(self, integration_id: UUID) -> None:
        """Hard-delete all ToolParameter records for tools owned by this integration."""
        tool_ids_query = select(Tool.id).where(Tool.integration_id == integration_id)
        await self.session.exec(delete(ToolParameter).where(col(ToolParameter.tool_id).in_(tool_ids_query)))

    async def _hard_delete_linked_tools(self, integration_id: UUID) -> None:
        """Hard-delete all Tool records owned by this integration."""
        await self.session.exec(
            delete(Tool).where(Tool.integration_id == integration_id)  # type: ignore[arg-type]
        )

    async def _hard_delete_linked_models(self, integration_id: UUID) -> None:
        """Hard-delete all LLMModel records owned by this integration."""
        await self.session.exec(
            delete(LLMModel).where(LLMModel.integration_id == integration_id)  # type: ignore[arg-type]
        )

    async def _sync_llm_models(
        self,
        integration: Integration,
        discovered_models: list[DiscoveredLLMModel],
        *,
        enabled_map: dict[str, bool] | None = None,
        default_model_id: str | None = None,
    ) -> tuple[int, int, int]:
        """Upsert LLMModel records from discovered models.

        Models that disappear from the provider are kept (not deleted)
        and their admin-controlled ``enabled`` state is left untouched,
        matching the MCP tool pattern.

        If ``enabled_map`` is provided, each model's enabled state is set
        according to the map (used during creation with user selections).
        Otherwise all new models default to enabled=True.

        If ``default_model_id`` is provided, that model is marked as the
        default and all others are unset. During refresh (no default_model_id),
        existing default state is preserved.

        Returns a (synced_count, updated_count, missing_count) tuple.
        """
        existing_query = await self.session.exec(select(LLMModel).where(LLMModel.integration_id == integration.id))
        existing_models = {m.model_id: m for m in existing_query.all()}
        found_ids: set[str] = set()
        synced_count = 0
        updated_count = 0

        now = datetime.now(UTC)
        for model_meta in discovered_models:
            found_ids.add(model_meta.id)
            logger.debug(
                "Processing discovered model",
                integration_id=str(integration.id),
                model_id=model_meta.id,
                model_name=model_meta.name,
                is_existing=model_meta.id in existing_models,
            )

            profile = lookup_model_profile(model_meta.id)

            if model_meta.id in existing_models:
                existing = existing_models[model_meta.id]
                existing.name = model_meta.name
                existing.description = model_meta.description
                existing.last_refreshed_at = now
                existing.updated_at = now
                existing.profile = profile
                if default_model_id is not None:
                    existing.is_default = model_meta.id == default_model_id
                updated_count += 1
            else:
                model_enabled = enabled_map.get(model_meta.id, True) if enabled_map else True
                new_model = LLMModel(
                    integration_id=integration.id,
                    model_id=model_meta.id,
                    name=model_meta.name,
                    description=model_meta.description,
                    enabled=model_enabled,
                    is_default=model_meta.id == default_model_id if default_model_id else False,
                    last_refreshed_at=now,
                    profile=profile,
                )
                self.session.add(new_model)
                synced_count += 1

        missing_count = sum(1 for mid in existing_models if mid not in found_ids)

        await self.session.flush()
        return synced_count, updated_count, missing_count


def _discovered_params_to_tool_params(
    discovered: list[DiscoveredToolParameter],
) -> list[ToolParameter]:
    """Convert DiscoveredToolParameter list to ToolParameter domain objects."""
    result: list[ToolParameter] = []
    for p in discovered:
        param_type = _str_to_tool_param_type(p.type)
        result.append(
            ToolParameter(
                name=p.name,
                type=param_type,
                description=p.description,
                required=p.required,
            )
        )
    return result


def _str_to_tool_param_type(type_str: str) -> ToolParameterType:
    """Map a JSON/string type name to ToolParameterType."""
    mapping: dict[str, ToolParameterType] = {
        "string": ToolParameterType.STRING,
        "number": ToolParameterType.NUMBER,
        "integer": ToolParameterType.NUMBER,
        "boolean": ToolParameterType.BOOLEAN,
        "object": ToolParameterType.OBJECT,
        "array": ToolParameterType.ARRAY,
    }
    result = mapping.get(type_str)
    if result is None:
        logger.warning("Unknown tool parameter type, defaulting to string", type_str=type_str)
        return ToolParameterType.STRING
    return result
