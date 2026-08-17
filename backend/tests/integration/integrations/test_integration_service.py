"""Unit tests for IntegrationService."""

from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.models import Project
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.integrations.exceptions import (
    IntegrationCredentialNotFoundError,
    IntegrationCredentialRequiredError,
    IntegrationCredentialTypeMismatchError,
    IntegrationNameConflictError,
    IntegrationNotFoundError,
)
from syntara.integrations.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationStatus,
    IntegrationSystemUpdate,
    IntegrationTestConnection,  # used by discover() service method
    IntegrationType,
    IntegrationUpdate,
)
from syntara.integrations.services.integration_service import IntegrationService

_UNRESTRICTED = AllowedProjectsResult(all_projects=True, project_ids=[])


@pytest.fixture
def integration_service(test_db_session: AsyncSession, test_user: User) -> IntegrationService:
    """Create an IntegrationService for testing."""
    return IntegrationService(test_db_session, test_user)


def _mcp_create(name: str = "Test MCP", **kwargs: object) -> IntegrationCreate:
    """Helper to build an IntegrationCreate for MCP Server."""
    defaults: dict[str, object] = {
        "name": name,
        "integration_type": IntegrationType.MCP_SERVER,
        "configuration": {"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
    }
    defaults.update(kwargs)
    return IntegrationCreate(**defaults)


class TestCreateIntegration:
    """Tests for IntegrationService.create_integration."""

    @pytest.mark.asyncio
    async def test_create_success(
        self, test_db_session: AsyncSession, test_user: User, integration_service: IntegrationService
    ) -> None:
        data = _mcp_create()
        result = await integration_service.create_integration(data)

        assert result.name == "Test MCP"
        assert result.integration_type == IntegrationType.MCP_SERVER
        assert result.validation_status == IntegrationStatus.UNKNOWN
        assert result.scope == IntegrationScope.GLOBAL
        assert result.enabled is True
        assert result.management_credential_id is None
        assert result.created_by == test_user.username

    @pytest.mark.asyncio
    async def test_create_llm_provider(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        credential_factory,
    ) -> None:
        ct = await credential_factory.create_type("LLM Provider")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)

        data = IntegrationCreate(
            name="Test LLM",
            integration_type=IntegrationType.LLM_PROVIDER,
            configuration={
                "integration_type": "llm_provider",
                "base_url": "http://localhost:11434",
                "provider_hint": "custom",
            },
            management_credential_id=cred.id,
        )
        result = await integration_service.create_integration(data)

        assert result.integration_type == IntegrationType.LLM_PROVIDER
        assert result.configuration.base_url == "http://localhost:11434"
        assert result.configuration.provider_hint == "custom"  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_create_aap(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        credential_factory,
    ) -> None:
        ct = await credential_factory.create_type("Ansible Automation Platform")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)

        data = IntegrationCreate(
            name="Test Gateway",
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            configuration={
                "integration_type": "ansible_automation_platform",
                "base_url": "https://gateway.example.com",
                "insecure_skip_tls_verify": True,
            },
            management_credential_id=cred.id,
        )
        result = await integration_service.create_integration(data)

        assert result.integration_type == IntegrationType.ANSIBLE_AUTOMATION_PLATFORM
        assert result.configuration.base_url == "https://gateway.example.com"
        assert result.configuration.insecure_skip_tls_verify is True

    @pytest.mark.asyncio
    async def test_create_duplicate_name_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        data = _mcp_create(name="Duplicate")
        await integration_service.create_integration(data)

        with pytest.raises(IntegrationNameConflictError, match="Integration with name 'Duplicate' already exists"):
            await integration_service.create_integration(data)

    @pytest.mark.asyncio
    async def test_create_default_scope_global(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        data = _mcp_create()
        result = await integration_service.create_integration(data)
        assert result.scope == IntegrationScope.GLOBAL

    @pytest.mark.asyncio
    async def test_create_with_project_scope(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        data = _mcp_create(name="Project Scoped", scope=IntegrationScope.PROJECT)
        result = await integration_service.create_integration(data)
        assert result.scope == IntegrationScope.PROJECT


class TestGetIntegration:
    """Tests for IntegrationService.get_integration."""

    @pytest.mark.asyncio
    async def test_get_success(self, test_db_session: AsyncSession, integration_service: IntegrationService) -> None:
        created = await integration_service.create_integration(_mcp_create())
        result = await integration_service.get_integration(created.id)

        assert result.id == created.id
        assert result.name == created.name

    @pytest.mark.asyncio
    async def test_get_not_found_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        with pytest.raises(IntegrationNotFoundError):
            await integration_service.get_integration(uuid4())

    @pytest.mark.asyncio
    async def test_get_deleted_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())
        await integration_service.delete_integration(created.id)

        with pytest.raises(IntegrationNotFoundError):
            await integration_service.get_integration(created.id)

    @pytest.mark.asyncio
    async def test_get_global_visible_to_restricted_caller(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        from syntara.authz.engine import AllowedProjectsResult

        created = await integration_service.create_integration(
            _mcp_create(name="Global Visible", scope=IntegrationScope.GLOBAL)
        )
        restricted = AllowedProjectsResult(all_projects=False, project_ids=[])
        result = await integration_service.get_integration(created.id, allowed_projects=restricted)
        assert result.id == created.id

    @pytest.mark.asyncio
    async def test_get_project_scoped_visible_when_assigned(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        from syntara.authz.engine import AllowedProjectsResult
        from syntara.authz.models import Project

        project = Project(name="visibility-project")
        test_db_session.add(project)
        await test_db_session.flush()

        created = await integration_service.create_integration(
            _mcp_create(name="Assigned", scope=IntegrationScope.PROJECT)
        )
        test_db_session.add(IntegrationProjectAssignment(integration_id=created.id, project_id=project.id))
        await test_db_session.flush()

        allowed = AllowedProjectsResult(all_projects=False, project_ids=[project.id])
        result = await integration_service.get_integration(created.id, allowed_projects=allowed)
        assert result.id == created.id

    @pytest.mark.asyncio
    async def test_get_project_scoped_not_visible_when_unassigned(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        from syntara.authz.engine import AllowedProjectsResult

        created = await integration_service.create_integration(
            _mcp_create(name="Unassigned", scope=IntegrationScope.PROJECT)
        )
        restricted = AllowedProjectsResult(all_projects=False, project_ids=[])

        with pytest.raises(IntegrationNotFoundError):
            await integration_service.get_integration(created.id, allowed_projects=restricted)


class TestListIntegrations:
    """Tests for IntegrationService.list_integrations."""

    @pytest.mark.asyncio
    async def test_list_returns_paginated_response(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        await integration_service.create_integration(_mcp_create(name="Integration A"))
        await integration_service.create_integration(_mcp_create(name="Integration B"))

        result = await integration_service.list_integrations(allowed_projects=_UNRESTRICTED)

        assert len(result.resources) == 2

    @pytest.mark.asyncio
    async def test_list_excludes_deleted(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        active = await integration_service.create_integration(_mcp_create(name="Active"))
        deleted = await integration_service.create_integration(_mcp_create(name="Deleted"))
        await integration_service.delete_integration(deleted.id)

        result = await integration_service.list_integrations(allowed_projects=_UNRESTRICTED)

        ids = {r.id for r in result.resources}
        assert active.id in ids
        assert deleted.id not in ids

    @pytest.mark.asyncio
    async def test_list_filter_by_integration_type(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        credential_factory,
    ) -> None:
        ct = await credential_factory.create_type("LLM Provider")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)

        await integration_service.create_integration(_mcp_create(name="MCP One"))
        await integration_service.create_integration(
            IntegrationCreate(
                name="LLM One",
                integration_type=IntegrationType.LLM_PROVIDER,
                configuration={
                    "integration_type": "llm_provider",
                    "base_url": "http://localhost:11434",
                    "provider_hint": "custom",
                },
                management_credential_id=cred.id,
            )
        )

        result = await integration_service.list_integrations(
            allowed_projects=_UNRESTRICTED, query_params_items=[("integration_type", "mcp_server")]
        )

        assert len(result.resources) == 1
        assert result.resources[0].integration_type == IntegrationType.MCP_SERVER

    @pytest.mark.asyncio
    async def test_list_filter_by_enabled(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        await integration_service.create_integration(_mcp_create(name="Enabled", enabled=True))
        disabled = await integration_service.create_integration(_mcp_create(name="Disabled", enabled=False))

        result = await integration_service.list_integrations(
            allowed_projects=_UNRESTRICTED, query_params_items=[("enabled", "false")]
        )

        assert len(result.resources) == 1
        assert result.resources[0].id == disabled.id

    @pytest.mark.asyncio
    async def test_list_sort_by_name(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        await integration_service.create_integration(_mcp_create(name="Zebra"))
        await integration_service.create_integration(_mcp_create(name="Alpha"))

        result = await integration_service.list_integrations(allowed_projects=_UNRESTRICTED, sort="name")

        names = [r.name for r in result.resources]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_list_include_total(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        await integration_service.create_integration(_mcp_create(name="One"))
        await integration_service.create_integration(_mcp_create(name="Two"))
        await integration_service.create_integration(_mcp_create(name="Three"))

        result = await integration_service.list_integrations(
            allowed_projects=_UNRESTRICTED, limit=2, include_total=True
        )

        assert len(result.resources) == 2
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_list_scope_filter_global_always_visible(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        from syntara.authz.engine import AllowedProjectsResult

        await integration_service.create_integration(_mcp_create(name="Global", scope=IntegrationScope.GLOBAL))
        await integration_service.create_integration(_mcp_create(name="Project Scoped", scope=IntegrationScope.PROJECT))

        # Caller has no project access — only the GLOBAL integration is visible
        no_projects = AllowedProjectsResult(all_projects=False, project_ids=[])
        result = await integration_service.list_integrations(allowed_projects=no_projects)

        assert len(result.resources) == 1
        assert result.resources[0].name == "Global"

    @pytest.mark.asyncio
    async def test_list_scope_filter_project_visible_with_assignment(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        from syntara.authz.engine import AllowedProjectsResult
        from syntara.authz.models import Project

        project = Project(name="my-project")
        test_db_session.add(project)
        await test_db_session.flush()

        await integration_service.create_integration(_mcp_create(name="Global", scope=IntegrationScope.GLOBAL))
        project_integration = await integration_service.create_integration(
            _mcp_create(name="Project Scoped", scope=IntegrationScope.PROJECT)
        )

        assignment = IntegrationProjectAssignment(integration_id=project_integration.id, project_id=project.id)
        test_db_session.add(assignment)
        await test_db_session.flush()

        allowed = AllowedProjectsResult(all_projects=False, project_ids=[project.id])
        result = await integration_service.list_integrations(allowed_projects=allowed)

        ids = {r.id for r in result.resources}
        assert project_integration.id in ids
        assert all(r.name in {"Global", "Project Scoped"} for r in result.resources)


class TestPatchIntegration:
    """Tests for IntegrationService.update_integration."""

    @pytest.mark.asyncio
    async def test_patch_partial_fields(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())
        patch = IntegrationUpdate(name="Updated Name", enabled=False)

        result = await integration_service.update_integration(created.id, patch)

        assert result.name == "Updated Name"
        assert result.enabled is False
        assert result.description == created.description

    @pytest.mark.asyncio
    async def test_patch_name_conflict_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        await integration_service.create_integration(_mcp_create(name="First"))
        second = await integration_service.create_integration(_mcp_create(name="Second"))

        with pytest.raises(IntegrationNameConflictError):
            await integration_service.update_integration(second.id, IntegrationUpdate(name="First"))

    @pytest.mark.asyncio
    async def test_patch_configuration_type_mismatch_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())
        patch = IntegrationUpdate(
            configuration={
                "integration_type": "llm_provider",
                "base_url": "https://api.openai.com",
                "provider_hint": "openai",
            },
        )

        with pytest.raises(SafeValueError, match="does not match integration type"):
            await integration_service.update_integration(created.id, patch)

    @pytest.mark.asyncio
    async def test_patch_configuration_matching_type_succeeds(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())
        patch = IntegrationUpdate(
            configuration={"integration_type": "mcp_server", "base_url": "https://updated.example.com"},
        )

        result = await integration_service.update_integration(created.id, patch)
        assert result.configuration.base_url == "https://updated.example.com"

    @pytest.mark.asyncio
    async def test_patch_not_found_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        with pytest.raises(IntegrationNotFoundError):
            await integration_service.update_integration(uuid4(), IntegrationUpdate(name="x"))


class TestUpdateValidationStatus:
    """Tests for IntegrationService.update_validation_status."""

    @pytest.mark.asyncio
    async def test_update_status_to_available(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())
        assert created.validation_status == IntegrationStatus.UNKNOWN

        result = await integration_service.update_validation_status(
            created.id, IntegrationSystemUpdate(validation_status=IntegrationStatus.AVAILABLE)
        )

        assert result.validation_status == IntegrationStatus.AVAILABLE

    @pytest.mark.asyncio
    async def test_update_status_to_error_with_message(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        result = await integration_service.update_validation_status(
            created.id,
            IntegrationSystemUpdate(validation_status=IntegrationStatus.ERROR, validation_error="Connection refused"),
        )

        assert result.validation_status == IntegrationStatus.ERROR
        assert result.validation_error == "Connection refused"

    @pytest.mark.asyncio
    async def test_available_transition_does_not_clear_validation_error(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())
        await integration_service.update_validation_status(
            created.id,
            IntegrationSystemUpdate(validation_status=IntegrationStatus.ERROR, validation_error="Connection refused"),
        )

        # Transition to AVAILABLE without explicitly clearing validation_error
        result = await integration_service.update_validation_status(
            created.id, IntegrationSystemUpdate(validation_status=IntegrationStatus.AVAILABLE)
        )

        assert result.validation_status == IntegrationStatus.AVAILABLE
        # validation_error is NOT automatically cleared — callers must explicitly set it to None
        assert result.validation_error == "Connection refused"

    @pytest.mark.asyncio
    async def test_update_not_found_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        with pytest.raises(IntegrationNotFoundError):
            await integration_service.update_validation_status(
                uuid4(), IntegrationSystemUpdate(validation_status=IntegrationStatus.AVAILABLE)
            )


class TestDeleteIntegration:
    """Tests for IntegrationService.delete_integration."""

    @pytest.mark.asyncio
    async def test_delete_removes_integration_row(
        self, test_db_session: AsyncSession, test_user: User, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())
        await integration_service.delete_integration(created.id)

        query = select(Integration).filter(Integration.id == created.id)  # type: ignore[arg-type]
        result = await test_db_session.exec(query)

        assert result.one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_removes_project_assignments(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = Project(name="test-project-for-assignments")
        test_db_session.add(project)
        await test_db_session.flush()

        created = await integration_service.create_integration(
            _mcp_create(name="With Assignments", scope=IntegrationScope.PROJECT)
        )

        assignment = IntegrationProjectAssignment(
            integration_id=created.id,
            project_id=project.id,
        )
        test_db_session.add(assignment)
        await test_db_session.flush()

        await integration_service.delete_integration(created.id)

        query = select(IntegrationProjectAssignment).filter(
            IntegrationProjectAssignment.integration_id == created.id,  # type: ignore[arg-type]
        )
        result = await test_db_session.exec(query)
        assert result.all() == []

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        with pytest.raises(IntegrationNotFoundError):
            await integration_service.delete_integration(uuid4())


class TestCredentialTypeValidation:
    """Tests for credential type validation at create/patch time."""

    @pytest.mark.asyncio
    async def test_create_with_valid_credential_type(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        credential_factory,
    ) -> None:
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)

        data = _mcp_create(management_credential_id=cred.id)
        result = await integration_service.create_integration(data)
        assert result.management_credential_id == cred.id

    @pytest.mark.asyncio
    async def test_create_with_mismatched_credential_type_raises(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        credential_factory,
    ) -> None:
        ct = await credential_factory.create_type("LLM Provider")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)

        data = _mcp_create(management_credential_id=cred.id)
        with pytest.raises(IntegrationCredentialTypeMismatchError, match="not valid for integration type 'mcp_server'"):
            await integration_service.create_integration(data)

    @pytest.mark.asyncio
    async def test_create_with_nonexistent_credential_raises(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        data = _mcp_create(management_credential_id=uuid4())
        with pytest.raises(IntegrationCredentialNotFoundError):
            await integration_service.create_integration(data)

    @pytest.mark.asyncio
    async def test_create_without_credential_skips_validation(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        data = _mcp_create()
        result = await integration_service.create_integration(data)
        assert result.management_credential_id is None

    @pytest.mark.asyncio
    async def test_patch_with_valid_credential_type(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        credential_factory,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)

        patch = IntegrationUpdate(management_credential_id=cred.id)
        result = await integration_service.update_integration(created.id, patch)
        assert result.management_credential_id == cred.id

    @pytest.mark.asyncio
    async def test_patch_with_mismatched_credential_type_raises(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        credential_factory,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        ct = await credential_factory.create_type("SSH Key")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)

        patch = IntegrationUpdate(management_credential_id=cred.id)
        with pytest.raises(IntegrationCredentialTypeMismatchError, match="not valid for integration type 'mcp_server'"):
            await integration_service.update_integration(created.id, patch)

    @pytest.mark.asyncio
    async def test_patch_without_credential_skips_validation(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())
        patch = IntegrationUpdate(name="Renamed")
        result = await integration_service.update_integration(created.id, patch)
        assert result.name == "Renamed"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("integration_type", "credential_type_name", "configuration"),
        [
            (
                IntegrationType.LLM_PROVIDER,
                "LLM Provider",
                {"integration_type": "llm_provider", "base_url": "https://llm.example.com", "provider_hint": "custom"},
            ),
            (
                IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
                "Ansible Automation Platform",
                {
                    "integration_type": "ansible_automation_platform",
                    "base_url": "https://gateway.example.com",
                    "insecure_skip_tls_verify": True,
                },
            ),
        ],
    )
    async def test_patch_clearing_credential_on_required_type_raises(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        credential_factory,
        integration_type: IntegrationType,
        credential_type_name: str,
        configuration: dict[str, object],
    ) -> None:
        ct = await credential_factory.create_type(credential_type_name)
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)

        created = await integration_service.create_integration(
            IntegrationCreate(
                name="Test Required Cred",
                integration_type=integration_type,
                configuration=configuration,
                management_credential_id=cred.id,
            )
        )

        patch = IntegrationUpdate(management_credential_id=None)
        with pytest.raises(IntegrationCredentialRequiredError):
            await integration_service.update_integration(created.id, patch)

    @pytest.mark.asyncio
    async def test_patch_clearing_credential_on_non_required_type_succeeds(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        credential_factory,
    ) -> None:
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)

        created = await integration_service.create_integration(_mcp_create(management_credential_id=cred.id))
        result = await integration_service.update_integration(
            created.id, IntegrationUpdate(management_credential_id=None)
        )
        assert result.management_credential_id is None


class TestDiscover:
    """Tests for IntegrationService.discover() (formerly test_connection)."""

    @pytest.fixture
    def mock_secret_service(self) -> object:
        from unittest.mock import AsyncMock

        return AsyncMock()

    @pytest.fixture
    def service_with_secrets(
        self, test_db_session: AsyncSession, test_user: User, mock_secret_service: object
    ) -> IntegrationService:
        return IntegrationService(test_db_session, test_user, mock_secret_service)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_nonexistent_credential_raises(
        self,
        test_db_session: AsyncSession,
        service_with_secrets: IntegrationService,
    ) -> None:
        data = IntegrationTestConnection(
            integration_type=IntegrationType.MCP_SERVER,
            configuration={"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
            credential_id=uuid4(),
        )
        with pytest.raises(IntegrationCredentialNotFoundError):
            await service_with_secrets.discover(data)

    @pytest.mark.asyncio
    async def test_credential_without_secret_raises(
        self,
        test_db_session: AsyncSession,
        service_with_secrets: IntegrationService,
        credential_factory,
    ) -> None:
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)
        assert cred.secret_id is None

        data = IntegrationTestConnection(
            integration_type=IntegrationType.MCP_SERVER,
            configuration={"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
            credential_id=cred.id,
        )
        with pytest.raises(IntegrationCredentialNotFoundError):
            await service_with_secrets.discover(data)

    @pytest.mark.asyncio
    async def test_missing_secret_service_raises(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        service = IntegrationService(test_db_session, test_user)
        data = IntegrationTestConnection(
            integration_type=IntegrationType.MCP_SERVER,
            configuration={"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
            credential_id=uuid4(),
        )
        with pytest.raises(RuntimeError, match="SecretService is required"):
            await service.discover(data)
