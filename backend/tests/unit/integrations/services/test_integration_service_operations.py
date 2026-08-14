"""Unit tests for IntegrationService operational methods.

Covers validate_integration(), discover(), refresh_resources(),
and _resolve_credential() — methods that interact with external adapters,
credentials, and audit dispatching.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.credentials.exceptions import CredentialDisabledError
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.integrations.adapters.protocol import (
    DiscoveredTool,
    DiscoveredToolParameter,
    DiscoverResult,
    ValidateResult,
)
from syntara.integrations.exceptions import (
    IntegrationCredentialNotFoundError,
    IntegrationCredentialRequiredError,
    IntegrationNotFoundError,
    IntegrationRefreshNotSupportedError,
)
from syntara.integrations.models.integration import (
    InitialToolSelection,
    Integration,
    IntegrationCreate,
    IntegrationRefreshStatus,
    IntegrationStatus,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import AAPConfiguration, LLMProviderConfiguration
from syntara.integrations.services.integration_service import IntegrationService
from syntara.tool_manager.models.tool import Tool, ToolStatus

SERVICE_MODULE = "syntara.integrations.services.integration_service"


@pytest.fixture
def secret_service() -> MagicMock:
    svc = MagicMock()
    svc.retrieve_secret = AsyncMock(return_value={"token": "test-token-value"})
    return svc


@pytest.fixture
def integration_service(
    test_db_session: AsyncSession, test_user: User, secret_service: MagicMock
) -> IntegrationService:
    return IntegrationService(test_db_session, test_user, secret_service)


@pytest.fixture
def integration_service_no_secrets(test_db_session: AsyncSession, test_user: User) -> IntegrationService:
    return IntegrationService(test_db_session, test_user)


def _mcp_create(name: str = "Test MCP", **kwargs: object) -> IntegrationCreate:
    defaults: dict[str, object] = {
        "name": name,
        "integration_type": IntegrationType.MCP_SERVER,
        "configuration": {"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
    }
    defaults.update(kwargs)
    return IntegrationCreate(**defaults)


async def _insert_integration_direct(
    session: AsyncSession,
    user: User,
    *,
    integration_type: IntegrationType,
    name: str = "Test Integration",
    base_url: str | None = None,
) -> Integration:
    """Insert an Integration directly, bypassing create_integration() validation.

    ``base_url`` overrides the default host; use it to plant a value that passes the
    format-only model validators but would fail the DNS-resolving SSRF check (simulating
    a host that resolved publicly at write time and later rebinds to a private target).
    """
    configuration: LLMProviderConfiguration | AAPConfiguration
    if integration_type == IntegrationType.LLM_PROVIDER:
        configuration = LLMProviderConfiguration(
            integration_type="llm_provider",
            base_url=base_url or "https://api.example.com",
            provider_hint="openai",
        )
    else:
        configuration = AAPConfiguration(
            integration_type="ansible_automation_platform",
            base_url=base_url or "https://aap.example.com",
        )

    integration = Integration(
        name=name,
        integration_type=integration_type,
        configuration=configuration,
        enabled=True,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(integration)
    await session.flush()
    return integration


async def _create_credential(
    session: AsyncSession, user: User, *, secret_id: str | None = None, with_secret: bool = True
) -> tuple[Credential, CredentialType]:
    from syntara.authz.models import Project

    project = Project(name=f"test-project-{uuid4().hex[:8]}", created_by=user.id, updated_by=user.id)
    session.add(project)
    await session.flush()

    cred_type = CredentialType(
        name=f"HTTP Bearer Token {uuid4().hex[:6]}",
        namespace=f"http_bearer_{uuid4().hex[:6]}",
        inputs={"fields": [{"id": "token", "label": "Token", "type": "string", "secret": True}]},
        injectors={"extra_vars": {"bearer_token": "{{ token }}"}},
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(cred_type)
    await session.flush()

    cred = Credential(
        name=f"Test Credential {uuid4().hex[:6]}",
        credential_type_id=cred_type.id,
        secret_id=uuid4() if with_secret else None,
        project_id=project.id,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(cred)
    await session.flush()
    return cred, cred_type


def _mock_runtime_settings(timeout: int = 10) -> AsyncMock:
    mock = MagicMock()
    mock.get = AsyncMock(return_value=timeout)
    return mock


class TestResolveCredential:
    """Tests for IntegrationService._resolve_credential."""

    @pytest.mark.asyncio
    async def test_resolves_credential_successfully(
        self, test_db_session: AsyncSession, test_user: User, secret_service: MagicMock
    ) -> None:
        cred_id = uuid4()
        cred_type_id = uuid4()

        mock_cred = MagicMock()
        mock_cred.secret_id = uuid4()
        mock_cred.credential_type_id = cred_type_id

        mock_cred_type = MagicMock()
        mock_cred_type.injectors = {"extra_vars": {"token": "{{ token }}"}}

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(
            side_effect=lambda model, _id: mock_cred if model == Credential else mock_cred_type
        )

        service = IntegrationService(mock_session, test_user, secret_service)
        result = await service._resolve_credential(cred_id)

        assert isinstance(result, dict)
        secret_service.retrieve_secret.assert_called_once_with(mock_cred.secret_id)

    @pytest.mark.asyncio
    async def test_raises_when_credential_not_found(
        self, test_db_session: AsyncSession, test_user: User, secret_service: MagicMock
    ) -> None:
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        service = IntegrationService(mock_session, test_user, secret_service)
        with pytest.raises(IntegrationCredentialNotFoundError):
            await service._resolve_credential(uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_credential_has_no_secret(
        self, test_db_session: AsyncSession, test_user: User, secret_service: MagicMock
    ) -> None:
        mock_cred = MagicMock()
        mock_cred.secret_id = None

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_cred)

        service = IntegrationService(mock_session, test_user, secret_service)
        with pytest.raises(IntegrationCredentialNotFoundError):
            await service._resolve_credential(uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_credential_type_not_found(
        self, test_db_session: AsyncSession, test_user: User, secret_service: MagicMock
    ) -> None:
        mock_cred = MagicMock()
        mock_cred.secret_id = uuid4()
        mock_cred.credential_type_id = uuid4()

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=lambda model, _id: mock_cred if model == Credential else None)

        service = IntegrationService(mock_session, test_user, secret_service)
        with pytest.raises(IntegrationCredentialNotFoundError):
            await service._resolve_credential(uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_no_secret_service(self, test_db_session: AsyncSession, test_user: User) -> None:
        mock_session = AsyncMock()
        service = IntegrationService(mock_session, test_user)

        with pytest.raises(RuntimeError, match="SecretService is required"):
            await service._resolve_credential(uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_credential_disabled(
        self, test_db_session: AsyncSession, test_user: User, secret_service: MagicMock
    ) -> None:
        mock_cred = MagicMock()
        mock_cred.secret_id = uuid4()
        mock_cred.credential_type_id = uuid4()
        mock_cred.enabled = False
        mock_cred.name = "Disabled Cred"

        mock_cred_type = MagicMock()
        mock_cred_type.injectors = {"extra_vars": {"token": "{{ token }}"}}

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(
            side_effect=lambda model, _id: mock_cred if model == Credential else mock_cred_type
        )

        service = IntegrationService(mock_session, test_user, secret_service)
        with pytest.raises(CredentialDisabledError):
            await service._resolve_credential(uuid4())

        secret_service.retrieve_secret.assert_not_called()


class TestValidateIntegration:
    """Tests for IntegrationService.validate_integration."""

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_successful_validation_sets_available(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.validate = AsyncMock(return_value=ValidateResult(success=True, checked_at=datetime.now(UTC)))
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        result = await integration_service.validate_integration(created.id)

        assert result.success is True
        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None
        assert integration.validation_status == IntegrationStatus.AVAILABLE
        assert integration.last_validated_at is not None

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_failed_validation_sets_error(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.validate = AsyncMock(
            return_value=ValidateResult(success=False, checked_at=datetime.now(UTC), error="Connection refused")
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        result = await integration_service.validate_integration(created.id)

        assert result.success is False
        assert result.error == "Connection refused"
        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None
        assert integration.validation_status == IntegrationStatus.ERROR
        assert integration.validation_error == "Connection refused"

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    async def test_not_found_dispatches_audit_and_raises(
        self,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        fake_id = uuid4()
        with pytest.raises(IntegrationNotFoundError):
            await integration_service.validate_integration(fake_id)

        mock_audit.dispatch.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_validation_without_credential_passes_empty_dict(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.validate = AsyncMock(return_value=ValidateResult(success=True, checked_at=datetime.now(UTC)))
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        await integration_service.validate_integration(created.id)

        mock_adapter.validate.assert_called_once_with({}, 10)

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_unexpected_exception_sets_error_status(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.validate = AsyncMock(side_effect=RuntimeError("DB pool exhausted"))
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        with pytest.raises(RuntimeError, match="DB pool exhausted"):
            await integration_service.validate_integration(created.id)

        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None
        assert integration.validation_status == IntegrationStatus.ERROR
        assert integration.validation_error == "Unexpected error during validation: RuntimeError"
        assert integration.last_validated_at is not None

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_credential_required_llm_sets_error_status_and_last_validated_at(
        self,
        mock_adapter_factory: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        test_user: User,
        integration_service: IntegrationService,
    ) -> None:
        """LLM integration with missing credential sets ERROR status and last_validated_at."""
        integration = await _insert_integration_direct(
            test_db_session, test_user, integration_type=IntegrationType.LLM_PROVIDER
        )
        await test_db_session.commit()

        with pytest.raises(IntegrationCredentialRequiredError):
            await integration_service.validate_integration(integration.id)

        refreshed = await test_db_session.get(Integration, integration.id)
        assert refreshed is not None
        assert refreshed.validation_status == IntegrationStatus.ERROR
        assert "require a management credential" in (refreshed.validation_error or "")
        assert refreshed.last_validated_at is not None
        mock_adapter_factory.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_credential_required_aap_sets_error_status(
        self,
        mock_adapter_factory: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        test_user: User,
        integration_service: IntegrationService,
    ) -> None:
        """AAP integration with missing credential sets ERROR status and last_validated_at."""
        integration = await _insert_integration_direct(
            test_db_session, test_user, integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM
        )
        await test_db_session.commit()

        with pytest.raises(IntegrationCredentialRequiredError):
            await integration_service.validate_integration(integration.id)

        refreshed = await test_db_session.get(Integration, integration.id)
        assert refreshed is not None
        assert refreshed.validation_status == IntegrationStatus.ERROR
        assert refreshed.last_validated_at is not None
        mock_adapter_factory.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_credential_required_llm_dispatches_audit_event(
        self,
        mock_adapter_factory: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        test_user: User,
        integration_service: IntegrationService,
    ) -> None:
        """Missing credential dispatches an audit event with the correct error type."""
        integration = await _insert_integration_direct(
            test_db_session, test_user, integration_type=IntegrationType.LLM_PROVIDER
        )
        await test_db_session.commit()

        with pytest.raises(IntegrationCredentialRequiredError):
            await integration_service.validate_integration(integration.id)

        mock_audit.dispatch.assert_called_once()
        event = mock_audit.dispatch.call_args[0][0]
        assert event.error_type == "IntegrationCredentialRequiredError"
        assert event.result_status == IntegrationStatus.ERROR
        assert event.integration_id == integration.id

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_mcp_without_credential_proceeds_to_validation(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """MCP integration without credential does not raise IntegrationCredentialRequiredError."""
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.validate = AsyncMock(return_value=ValidateResult(success=True, checked_at=datetime.now(UTC)))
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        result = await integration_service.validate_integration(created.id)

        assert result.success is True
        mock_adapter_factory.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_disabled_credential_sets_error_status_and_last_validated_at(
        self,
        mock_adapter_factory: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """Integration with disabled credential sets ERROR status and last_validated_at."""
        created = await integration_service.create_integration(_mcp_create())
        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None

        cred, _ = await _create_credential(test_db_session, integration_service.user, with_secret=False)
        integration.management_credential_id = cred.id
        await test_db_session.flush()
        mock_audit.reset_mock()

        with (
            patch.object(
                integration_service,
                "_resolve_credential",
                new_callable=AsyncMock,
                side_effect=CredentialDisabledError("Test Cred"),
            ),
            pytest.raises(CredentialDisabledError),
        ):
            await integration_service.validate_integration(created.id)

        refreshed = await test_db_session.get(Integration, created.id)
        assert refreshed is not None
        assert refreshed.validation_status == IntegrationStatus.ERROR
        assert "disabled" in (refreshed.validation_error or "").lower()
        assert refreshed.last_validated_at is not None
        mock_adapter_factory.assert_not_called()
        mock_audit.dispatch.assert_called_once()
        event = mock_audit.dispatch.call_args[0][0]
        assert event.error_type == "CredentialDisabledError"


class TestDiscover:
    """Tests for IntegrationService.discover."""

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_successful_discover_returns_tools(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[
                    DiscoveredTool(name="tool_a", description="Tool A"),
                    DiscoveredTool(name="tool_b", description="Tool B"),
                ],
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        from syntara.integrations.models.integration import IntegrationTestConnection
        from syntara.integrations.models.integration_configuration import MCPServerConfigurationInput

        cred_id = uuid4()
        data = IntegrationTestConnection(
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfigurationInput(
                integration_type=IntegrationType.MCP_SERVER,
                base_url="http://localhost:8080",
            ),
            credential_id=cred_id,
        )

        with patch.object(
            integration_service, "_resolve_credential", new_callable=AsyncMock, return_value={"token": "t"}
        ):
            result = await integration_service.discover(data)

        assert result.success is True
        assert result.discovered_tools is not None
        assert len(result.discovered_tools) == 2

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_failed_discover_dispatches_audit(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Timeout",
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        from syntara.integrations.models.integration import IntegrationTestConnection
        from syntara.integrations.models.integration_configuration import MCPServerConfigurationInput

        cred_id = uuid4()
        data = IntegrationTestConnection(
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfigurationInput(
                integration_type=IntegrationType.MCP_SERVER,
                base_url="http://localhost:8080",
            ),
            credential_id=cred_id,
        )

        with patch.object(
            integration_service, "_resolve_credential", new_callable=AsyncMock, return_value={"token": "t"}
        ):
            result = await integration_service.discover(data)

        assert result.success is False
        mock_audit.dispatch.assert_called_once()


class TestRefreshIntegrationResources:
    """Tests for IntegrationService.refresh_resources."""

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_successful_refresh_creates_tools(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[
                    DiscoveredTool(
                        name="tool_a",
                        description="Tool A",
                        parameters=[
                            DiscoveredToolParameter(name="param1", type="string"),
                        ],
                    ),
                    DiscoveredTool(name="tool_b", description="Tool B"),
                ],
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        result = await integration_service.refresh_resources(created.id)

        assert result.synced_count == 2
        assert result.updated_count == 0
        assert result.missing_count == 0
        assert result.refreshed_at is not None

        tools = (await test_db_session.exec(select(Tool).where(Tool.integration_id == created.id))).all()
        assert len(tools) == 2

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_refresh_updates_existing_tools(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[DiscoveredTool(name="tool_a", description="Original")],
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        await integration_service.refresh_resources(created.id)

        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[DiscoveredTool(name="tool_a", description="Updated")],
            )
        )

        result = await integration_service.refresh_resources(created.id)

        assert result.synced_count == 0
        assert result.updated_count == 1

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_refresh_marks_missing_tools_without_disabling(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """A vanished tool is counted, kept with enabled unchanged, and marked MISSING."""
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[
                    DiscoveredTool(name="tool_a", description="A"),
                    DiscoveredTool(name="tool_b", description="B"),
                ],
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        await integration_service.refresh_resources(created.id)

        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[DiscoveredTool(name="tool_a", description="A")],
            )
        )

        result = await integration_service.refresh_resources(created.id)

        assert result.missing_count == 1

        # tool_b vanished: row kept, enabled untouched (admin-controlled), status MISSING.
        tool_b = (
            await test_db_session.exec(select(Tool).where(Tool.integration_id == created.id, Tool.name == "tool_b"))
        ).one()
        assert tool_b.status == ToolStatus.MISSING
        assert tool_b.enabled is True

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_failed_refresh_sets_error_status(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Connection refused",
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        result = await integration_service.refresh_resources(created.id)

        assert result.synced_count == 0
        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None
        assert integration.refresh_status == IntegrationRefreshStatus.ERROR
        assert integration.refresh_error == "Connection refused"

    @pytest.mark.asyncio
    async def test_refresh_unsupported_type_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService, test_user: User
    ) -> None:
        integration = Integration(
            name="Ansible Automation Platform",
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            configuration={
                "integration_type": "ansible_automation_platform",
                "base_url": "https://gateway.example.com",
            },
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        test_db_session.add(integration)
        await test_db_session.flush()

        with pytest.raises(IntegrationRefreshNotSupportedError):
            await integration_service.refresh_resources(integration.id)

    @pytest.mark.asyncio
    async def test_refresh_not_found_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        with pytest.raises(IntegrationNotFoundError):
            await integration_service.refresh_resources(uuid4())

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_successful_refresh_sets_available_status(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[],
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        await integration_service.refresh_resources(created.id)

        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None
        assert integration.refresh_status == IntegrationRefreshStatus.AVAILABLE
        assert integration.refresh_error is None
        assert integration.last_refreshed_at is not None
        assert integration.last_successful_refresh_at == integration.last_refreshed_at

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_create_with_discovered_tools_sets_both_timestamps(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """Creating an MCP integration with pre-discovered tools stamps both refresh timestamps.

        The UI reads last_successful_refresh_at, so a freshly-created integration must not show "Never".
        """
        created = await integration_service.create_integration(
            _mcp_create(discovered_tools=[InitialToolSelection(name="tool_a")])
        )

        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None
        assert integration.last_refreshed_at is not None
        assert integration.last_successful_refresh_at is not None
        assert integration.last_successful_refresh_at == integration.last_refreshed_at

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_refresh_preserves_enabled_state(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """Tools that were disabled by the admin stay disabled after refresh."""
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[
                    DiscoveredTool(name="tool_a", description="A"),
                    DiscoveredTool(name="tool_b", description="B"),
                ],
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        await integration_service.refresh_resources(created.id)

        # Admin disables tool_a
        tools = (
            await test_db_session.exec(select(Tool).where(Tool.integration_id == created.id, Tool.name == "tool_a"))
        ).one()
        tools.enabled = False
        await test_db_session.flush()

        # Refresh again with same tools
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[
                    DiscoveredTool(name="tool_a", description="A updated"),
                    DiscoveredTool(name="tool_b", description="B updated"),
                ],
            )
        )

        await integration_service.refresh_resources(created.id)

        # tool_a should still be disabled, tool_b should still be enabled
        tool_a = (
            await test_db_session.exec(select(Tool).where(Tool.integration_id == created.id, Tool.name == "tool_a"))
        ).one()
        tool_b = (
            await test_db_session.exec(select(Tool).where(Tool.integration_id == created.id, Tool.name == "tool_b"))
        ).one()
        assert tool_a.enabled is False
        assert tool_a.description == "A updated"
        assert tool_b.enabled is True
        assert tool_b.description == "B updated"

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_refresh_restores_missing_tool_status_to_available(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """A MISSING tool that reappears is restored to AVAILABLE.

        Discovery never overrides the admin-controlled enabled flag through either transition.
        """
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[DiscoveredTool(name="tool_a", description="A")],
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        await integration_service.refresh_resources(created.id)

        # Admin disables tool_a — a human decision discovery must respect.
        tool_a = (
            await test_db_session.exec(select(Tool).where(Tool.integration_id == created.id, Tool.name == "tool_a"))
        ).one()
        tool_a.enabled = False
        await test_db_session.flush()

        # Tool disappears on next refresh — marked MISSING, enabled left untouched.
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[],
            )
        )
        result = await integration_service.refresh_resources(created.id)
        assert result.missing_count == 1

        tool_a = (
            await test_db_session.exec(select(Tool).where(Tool.integration_id == created.id, Tool.name == "tool_a"))
        ).one()
        assert tool_a.status == ToolStatus.MISSING
        assert tool_a.enabled is False  # admin's disable preserved, not re-applied by discovery

        # Tool reappears on next refresh — status restored, admin's disable still preserved.
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[DiscoveredTool(name="tool_a", description="A is back")],
            )
        )
        result = await integration_service.refresh_resources(created.id)
        assert result.updated_count == 1

        tool_a = (
            await test_db_session.exec(select(Tool).where(Tool.integration_id == created.id, Tool.name == "tool_a"))
        ).one()
        assert tool_a.status == ToolStatus.AVAILABLE
        assert tool_a.description == "A is back"
        assert tool_a.enabled is False  # refresh never overrides admin's disable

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_unexpected_exception_sets_error_status(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(side_effect=RuntimeError("Session pool timeout"))
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        with pytest.raises(RuntimeError, match="Session pool timeout"):
            await integration_service.refresh_resources(created.id)

        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None
        assert integration.refresh_status == IntegrationRefreshStatus.ERROR
        assert integration.refresh_error == "Unexpected error during refresh: RuntimeError"
        assert integration.last_refreshed_at is not None

    @pytest.mark.asyncio
    async def test_refresh_skips_recently_refreshed_when_skip_if_recent(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """With skip_if_recent=True, an integration refreshed within 60s is skipped."""
        created = await integration_service.create_integration(_mcp_create())

        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None
        integration.last_refreshed_at = datetime.now(UTC) - timedelta(seconds=10)
        await test_db_session.flush()

        result = await integration_service.refresh_resources(created.id, skip_if_recent=True)

        assert result.synced_count == 0
        assert result.updated_count == 0
        assert result.missing_count == 0
        assert result.refreshed_at is not None

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_manual_refresh_ignores_staleness_guard(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """Without skip_if_recent, a recent refresh does not prevent a new one."""
        created = await integration_service.create_integration(_mcp_create())

        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None
        integration.last_refreshed_at = datetime.now(UTC) - timedelta(seconds=10)
        await test_db_session.flush()

        mock_adapter = AsyncMock()
        mock_adapter.discover = AsyncMock(
            return_value=DiscoverResult(
                success=True,
                checked_at=datetime.now(UTC),
                discovered_tools=[DiscoveredTool(name="tool_a", description="A")],
            )
        )
        mock_adapter_factory.return_value = mock_adapter
        mock_settings.return_value = _mock_runtime_settings()

        result = await integration_service.refresh_resources(created.id)

        assert result.synced_count == 1

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_credential_required_llm_sets_refresh_error_status(
        self,
        mock_adapter_factory: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        test_user: User,
        integration_service: IntegrationService,
    ) -> None:
        """LLM integration with missing credential sets refresh ERROR and last_refreshed_at."""
        integration = await _insert_integration_direct(
            test_db_session, test_user, integration_type=IntegrationType.LLM_PROVIDER
        )
        await test_db_session.commit()

        with pytest.raises(IntegrationCredentialRequiredError):
            await integration_service.refresh_resources(integration.id)

        refreshed = await test_db_session.get(Integration, integration.id)
        assert refreshed is not None
        assert refreshed.refresh_status == IntegrationRefreshStatus.ERROR
        assert "require a management credential" in (refreshed.refresh_error or "")
        assert refreshed.last_refreshed_at is not None
        mock_adapter_factory.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_credential_required_llm_refresh_dispatches_audit_event(
        self,
        mock_adapter_factory: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        test_user: User,
        integration_service: IntegrationService,
    ) -> None:
        """Missing credential on refresh dispatches an audit event with the correct error type."""
        integration = await _insert_integration_direct(
            test_db_session, test_user, integration_type=IntegrationType.LLM_PROVIDER
        )
        await test_db_session.commit()

        with pytest.raises(IntegrationCredentialRequiredError):
            await integration_service.refresh_resources(integration.id)

        mock_audit.dispatch.assert_called_once()
        event = mock_audit.dispatch.call_args[0][0]
        assert event.error_type == "IntegrationCredentialRequiredError"
        assert event.result_status == IntegrationRefreshStatus.ERROR
        assert event.integration_id == integration.id

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_disabled_credential_sets_refresh_error_status(
        self,
        mock_adapter_factory: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """Refresh with disabled credential sets ERROR refresh status and last_refreshed_at."""
        created = await integration_service.create_integration(_mcp_create())
        integration = await test_db_session.get(Integration, created.id)
        assert integration is not None

        cred, _ = await _create_credential(test_db_session, integration_service.user, with_secret=False)
        integration.management_credential_id = cred.id
        await test_db_session.flush()
        mock_audit.reset_mock()

        with (
            patch.object(
                integration_service,
                "_resolve_credential",
                new_callable=AsyncMock,
                side_effect=CredentialDisabledError("Test Cred"),
            ),
            pytest.raises(CredentialDisabledError),
        ):
            await integration_service.refresh_resources(created.id)

        refreshed = await test_db_session.get(Integration, created.id)
        assert refreshed is not None
        assert refreshed.refresh_status == IntegrationRefreshStatus.ERROR
        assert "disabled" in (refreshed.refresh_error or "").lower()
        assert refreshed.last_refreshed_at is not None
        mock_adapter_factory.assert_not_called()
        mock_audit.dispatch.assert_called_once()
        event = mock_audit.dispatch.call_args[0][0]
        assert event.error_type == "CredentialDisabledError"


@pytest.mark.ssrf_enforced
class TestRequestTimeSsrfRevalidation:
    """Request-time SSRF re-check before adapter dispatch (guards DNS rebinding).

    Write-time validation is only a snapshot: a host that resolves publicly at create
    can later rebind to a private/metadata target. These integrations are inserted with
    a base_url that passes the format-only model validators but resolves to the cloud
    metadata IP, so only the request-time re-check can catch it. The check lives in the
    service (type-agnostic), so it covers AAP and LLM — which have no adapter-level
    validate_safe_url — not just MCP.
    """

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_validate_rejects_rebound_host_before_dispatch(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        test_user: User,
    ) -> None:
        integration = await _insert_integration_direct(
            test_db_session,
            test_user,
            integration_type=IntegrationType.LLM_PROVIDER,
            base_url="https://169.254.169.254",
        )
        cred, _ = await _create_credential(test_db_session, integration_service.user, with_secret=False)
        integration.management_credential_id = cred.id
        await test_db_session.flush()
        mock_settings.return_value = _mock_runtime_settings()

        with (
            patch.object(integration_service, "_resolve_credential", new_callable=AsyncMock, return_value={}),
            pytest.raises(SafeValueError, match="private, reserved, or cloud metadata"),
        ):
            await integration_service.validate_integration(integration.id)

        mock_adapter_factory.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{SERVICE_MODULE}.AuditEventDispatcher")
    @patch(f"{SERVICE_MODULE}.get_runtime_settings")
    @patch(f"{SERVICE_MODULE}.create_health_check_adapter")
    async def test_refresh_rejects_rebound_host_before_dispatch(
        self,
        mock_adapter_factory: MagicMock,
        mock_settings: MagicMock,
        mock_audit: MagicMock,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        test_user: User,
    ) -> None:
        integration = await _insert_integration_direct(
            test_db_session,
            test_user,
            integration_type=IntegrationType.LLM_PROVIDER,
            base_url="https://169.254.169.254",
        )
        cred, _ = await _create_credential(test_db_session, integration_service.user, with_secret=False)
        integration.management_credential_id = cred.id
        await test_db_session.flush()
        mock_settings.return_value = _mock_runtime_settings()

        with (
            patch.object(integration_service, "_resolve_credential", new_callable=AsyncMock, return_value={}),
            pytest.raises(SafeValueError, match="private, reserved, or cloud metadata"),
        ):
            await integration_service.refresh_resources(integration.id)

        mock_adapter_factory.assert_not_called()
