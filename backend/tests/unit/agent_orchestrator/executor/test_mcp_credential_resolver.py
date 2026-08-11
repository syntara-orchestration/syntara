"""Unit tests for InvocationExecutor MCP credential resolver.

Verifies that _make_mcp_credential_resolver:
- Uses execution credential from integration_connections when configured for an integration
- Returns None for integrations not listed in integration_connections (no management credential fallback)
- Returns None when integration_connections is None/empty (no management credential fallback)

Also tests eager credential validation (_validate_credentials_eagerly):
- Validates existence, enabled, project membership, type, and secret data
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr

from syntara.agent_orchestrator.exceptions import CredentialResolutionError
from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor
from syntara.agent_orchestrator.models import InvocationStatus
from syntara.agent_orchestrator.models.context_data import InvocationContextData, InvocationMetadata
from syntara.agent_orchestrator.services.orchestration_service import OrchestrationService
from syntara.workflows.workflow_engine.models.workflow_definition import IntegrationConnectionConfig


def _make_executor(mock_session: MagicMock | None = None) -> InvocationExecutor:
    """Build a minimal InvocationExecutor for testing."""
    if mock_session is None:
        mock_session = MagicMock()

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[MagicMock, None]:
        yield mock_session

    executor = InvocationExecutor.__new__(InvocationExecutor)
    executor.get_async_session_context = mock_session_ctx
    executor.session_factory = mock_session_ctx  # type: ignore[assignment]  # used by ContextManagerPlanner
    return executor


class TestMCPCredentialResolverWithMCPConnections:
    """Tests for execution credential resolution via integration_connections."""

    @pytest.mark.asyncio
    async def test_uses_execution_credential_for_listed_integration(self) -> None:
        """When integration_id is in integration_connections, execution credential is used."""
        integration_id = uuid4()
        exec_cred_id = str(uuid4())
        integration_connections = [
            IntegrationConnectionConfig(integration_id=str(integration_id), credential_id=exec_cred_id)
        ]

        executor = _make_executor()

        with patch.object(
            executor,
            "_resolve_mcp_execution_credential",
            new_callable=AsyncMock,
            return_value="exec-bearer-token",
        ) as mock_resolve:
            resolver = executor._make_mcp_credential_resolver(integration_connections)
            result = await resolver(integration_id)

        assert result == "exec-bearer-token"
        mock_resolve.assert_called_once_with(exec_cred_id)

    @pytest.mark.asyncio
    async def test_returns_none_for_unlisted_integration(self) -> None:
        """Integrations not in integration_connections return None — no management credential fallback."""
        listed_integration = uuid4()
        unlisted_integration = uuid4()
        integration_connections = [
            IntegrationConnectionConfig(integration_id=str(listed_integration), credential_id=str(uuid4()))
        ]

        executor = _make_executor()

        with patch.object(executor, "_resolve_mcp_execution_credential", new_callable=AsyncMock):
            resolver = executor._make_mcp_credential_resolver(integration_connections)
            result = await resolver(unlisted_integration)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_integration_connections(self) -> None:
        """Without integration_connections, all integrations return None — no management credential fallback."""
        integration_id = uuid4()
        executor = _make_executor()

        resolver = executor._make_mcp_credential_resolver(None)
        result = await resolver(integration_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_propagates_credential_resolution_error_from_resolution(self) -> None:
        """CredentialResolutionError raised by _resolve_mcp_execution_credential propagates to the caller."""
        from syntara.agent_orchestrator.exceptions import CredentialResolutionError

        integration_id = uuid4()
        integration_connections = [
            IntegrationConnectionConfig(integration_id=str(integration_id), credential_id=str(uuid4()))
        ]
        executor = _make_executor()

        with patch.object(
            executor,
            "_resolve_mcp_execution_credential",
            new_callable=AsyncMock,
            side_effect=CredentialResolutionError("credential not found"),
        ):
            resolver = executor._make_mcp_credential_resolver(integration_connections)
            with pytest.raises(CredentialResolutionError):
                await resolver(integration_id)


class TestIntegrationConnectionConfig:
    """Tests for IntegrationConnectionConfig model in AgenticExecutorParameters."""

    def test_mcp_connection_config_validates(self) -> None:
        from syntara.workflows.workflow_engine.models.workflow_definition import IntegrationConnectionConfig

        conn = IntegrationConnectionConfig(
            integration_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            credential_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        )
        assert conn.integration_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        assert conn.credential_id == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    def test_agentic_executor_config_accepts_integration_connections(self) -> None:
        from syntara.workflows.workflow_engine.models.workflow_definition import AgenticExecutorParameters

        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "Test",
                "integration_connections": [
                    {
                        "integration_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "credential_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    }
                ],
            }
        )
        assert config.integration_connections is not None
        assert len(config.integration_connections) == 1
        assert config.integration_connections[0].integration_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    def test_agentic_executor_config_without_integration_connections(self) -> None:
        from syntara.workflows.workflow_engine.models.workflow_definition import AgenticExecutorParameters

        config = AgenticExecutorParameters.model_validate({"prompt": "Test"})
        assert config.integration_connections is None

    def test_agentic_executor_config_with_multiple_connections(self) -> None:
        from syntara.workflows.workflow_engine.models.workflow_definition import AgenticExecutorParameters

        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "Test",
                "integration_connections": [
                    {
                        "integration_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "credential_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    },
                    {
                        "integration_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "credential_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                    },
                ],
            }
        )
        assert config.integration_connections is not None
        assert len(config.integration_connections) == 2


class TestInitOrchestrationToolSelectionExtraction:
    """Tests that _init_orchestration correctly extracts tool selection from InvocationMetadata.

    Verifies that tool_selection_strategy and tool_selections are read from
    ctx.metadata and forwarded to OrchestrationService.
    """

    @pytest.mark.asyncio
    async def test_tool_selections_forwarded_to_orchestration_service(self) -> None:
        """tool_selection_strategy and tool_selections in ctx.metadata reach OrchestrationService."""
        executor = _make_executor()

        ctx = InvocationContextData.model_validate(
            {
                "metadata": {
                    "tool_selection_strategy": "SELECTED",
                    "tool_selections": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
                }
            }
        )

        invocation = MagicMock()
        invocation.id = uuid4()

        captured: dict[str, object] = {}

        def capture_service(**kwargs: object) -> MagicMock:
            captured.update(kwargs)
            return MagicMock(spec=OrchestrationService)

        mock_llm = MagicMock()
        mock_llm.openai_api_base = "https://openrouter.ai/api/v1"
        mock_llm.model_name = "test-model"

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(mock_llm, None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService",
                side_effect=capture_service,
            ),
        ):
            await executor._init_orchestration(invocation, ctx)

        assert captured.get("tool_selection_strategy") == "SELECTED"
        assert captured.get("tool_selections") == ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]

    @pytest.mark.asyncio
    async def test_none_strategy_when_metadata_absent(self) -> None:
        """When ctx.metadata is None, OrchestrationService receives "NONE" strategy and empty list."""
        executor = _make_executor()
        ctx = InvocationContextData.model_validate({})

        invocation = MagicMock()
        invocation.id = uuid4()

        captured: dict[str, object] = {}

        def capture_service(**kwargs: object) -> MagicMock:
            captured.update(kwargs)
            return MagicMock(spec=OrchestrationService)

        mock_llm = MagicMock()
        mock_llm.openai_api_base = "https://openrouter.ai/api/v1"
        mock_llm.model_name = "test-model"

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(mock_llm, None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService",
                side_effect=capture_service,
            ),
        ):
            await executor._init_orchestration(invocation, ctx)

        assert captured.get("tool_selection_strategy") == "NONE"
        assert captured.get("tool_selections") == []


def _make_credential_mock(
    *,
    cred_id: UUID | None = None,
    name: str = "test-cred",
    enabled: bool = True,
    project_id: UUID | None = None,
    type_name: str = "HTTP Bearer Token",
    secret_id: UUID | None = None,
) -> MagicMock:
    """Build a mock Credential with credential_type relationship."""
    cred = MagicMock()
    cred.id = cred_id or uuid4()
    cred.name = name
    cred.enabled = enabled
    cred.project_id = project_id or uuid4()
    cred.secret_id = secret_id if secret_id is not None else uuid4()
    cred.credential_type = MagicMock()
    cred.credential_type.name = type_name
    return cred


class TestEagerCredentialValidation:
    """Tests for _validate_credentials_eagerly."""

    @pytest.mark.asyncio
    async def test_valid_llm_and_mcp_credentials_pass(self) -> None:
        project_id = uuid4()
        llm_cred_id = uuid4()
        mcp_cred_id = uuid4()

        llm_cred = _make_credential_mock(cred_id=llm_cred_id, project_id=project_id, type_name="LLM Provider")
        mcp_cred = _make_credential_mock(cred_id=mcp_cred_id, project_id=project_id, type_name="HTTP Bearer Token")

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [llm_cred, mcp_cred]
        mock_session.exec = AsyncMock(return_value=mock_result)

        executor = _make_executor(mock_session)
        meta = InvocationMetadata(
            credential_id=SecretStr(str(llm_cred_id)),
            integration_connections=[
                IntegrationConnectionConfig(integration_id=str(uuid4()), credential_id=str(mcp_cred_id))
            ],
        )

        await executor._validate_credentials_eagerly(meta, project_id)

    @pytest.mark.asyncio
    async def test_missing_credential_fails(self) -> None:
        project_id = uuid4()
        missing_cred_id = uuid4()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)

        executor = _make_executor(mock_session)
        meta = InvocationMetadata(
            integration_connections=[
                IntegrationConnectionConfig(integration_id=str(uuid4()), credential_id=str(missing_cred_id))
            ],
        )

        with pytest.raises(CredentialResolutionError, match="not found"):
            await executor._validate_credentials_eagerly(meta, project_id)

    @pytest.mark.asyncio
    async def test_disabled_credential_fails(self) -> None:
        project_id = uuid4()
        cred_id = uuid4()
        cred = _make_credential_mock(cred_id=cred_id, project_id=project_id, enabled=False)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [cred]
        mock_session.exec = AsyncMock(return_value=mock_result)

        executor = _make_executor(mock_session)
        meta = InvocationMetadata(
            integration_connections=[
                IntegrationConnectionConfig(integration_id=str(uuid4()), credential_id=str(cred_id))
            ],
        )

        with pytest.raises(CredentialResolutionError, match="disabled"):
            await executor._validate_credentials_eagerly(meta, project_id)

    @pytest.mark.asyncio
    async def test_wrong_project_fails(self) -> None:
        project_id = uuid4()
        other_project_id = uuid4()
        cred_id = uuid4()
        cred = _make_credential_mock(cred_id=cred_id, project_id=other_project_id)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [cred]
        mock_session.exec = AsyncMock(return_value=mock_result)

        executor = _make_executor(mock_session)
        meta = InvocationMetadata(
            integration_connections=[
                IntegrationConnectionConfig(integration_id=str(uuid4()), credential_id=str(cred_id))
            ],
        )

        with pytest.raises(CredentialResolutionError, match="does not belong to this project"):
            await executor._validate_credentials_eagerly(meta, project_id)

    @pytest.mark.asyncio
    async def test_wrong_credential_type_fails(self) -> None:
        project_id = uuid4()
        cred_id = uuid4()
        cred = _make_credential_mock(cred_id=cred_id, project_id=project_id, type_name="LLM Provider")

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [cred]
        mock_session.exec = AsyncMock(return_value=mock_result)

        executor = _make_executor(mock_session)
        meta = InvocationMetadata(
            integration_connections=[
                IntegrationConnectionConfig(integration_id=str(uuid4()), credential_id=str(cred_id))
            ],
        )

        with pytest.raises(CredentialResolutionError, match="expected one of"):
            await executor._validate_credentials_eagerly(meta, project_id)

    @pytest.mark.asyncio
    async def test_no_secret_data_fails(self) -> None:
        project_id = uuid4()
        cred_id = uuid4()
        cred = _make_credential_mock(cred_id=cred_id, project_id=project_id, secret_id=None)
        cred.secret_id = None

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [cred]
        mock_session.exec = AsyncMock(return_value=mock_result)

        executor = _make_executor(mock_session)
        meta = InvocationMetadata(
            integration_connections=[
                IntegrationConnectionConfig(integration_id=str(uuid4()), credential_id=str(cred_id))
            ],
        )

        with pytest.raises(CredentialResolutionError, match="no stored secret data"):
            await executor._validate_credentials_eagerly(meta, project_id)

    @pytest.mark.asyncio
    async def test_no_credentials_skipped(self) -> None:
        executor = _make_executor()
        meta = InvocationMetadata()

        await executor._validate_credentials_eagerly(meta, uuid4())

    @pytest.mark.asyncio
    async def test_invalid_llm_credential_uuid_fails(self) -> None:
        executor = _make_executor()
        meta = InvocationMetadata(credential_id=SecretStr("not-a-uuid"))
        project_id = uuid4()

        with pytest.raises(CredentialResolutionError, match="Invalid credential ID"):
            await executor._validate_credentials_eagerly(meta, project_id)

    @pytest.mark.asyncio
    async def test_llm_credential_only_passes(self) -> None:
        """LLM credential without any MCP connections validates successfully."""
        project_id = uuid4()
        llm_cred_id = uuid4()
        llm_cred = _make_credential_mock(cred_id=llm_cred_id, project_id=project_id, type_name="LLM Provider")

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [llm_cred]
        mock_session.exec = AsyncMock(return_value=mock_result)

        executor = _make_executor(mock_session)
        meta = InvocationMetadata(credential_id=SecretStr(str(llm_cred_id)))

        await executor._validate_credentials_eagerly(meta, project_id)

    @pytest.mark.asyncio
    async def test_multiple_mcp_credentials_fails_on_first_bad(self) -> None:
        """When multiple MCP credentials are present, a single bad one fails the whole check."""
        project_id = uuid4()
        good_cred_id = uuid4()
        bad_cred_id = uuid4()

        good_cred = _make_credential_mock(cred_id=good_cred_id, project_id=project_id)
        bad_cred = _make_credential_mock(cred_id=bad_cred_id, project_id=project_id, enabled=False)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [good_cred, bad_cred]
        mock_session.exec = AsyncMock(return_value=mock_result)

        executor = _make_executor(mock_session)
        meta = InvocationMetadata(
            integration_connections=[
                IntegrationConnectionConfig(integration_id=str(uuid4()), credential_id=str(good_cred_id)),
                IntegrationConnectionConfig(integration_id=str(uuid4()), credential_id=str(bad_cred_id)),
            ],
        )

        with pytest.raises(CredentialResolutionError, match="disabled"):
            await executor._validate_credentials_eagerly(meta, project_id)

    @pytest.mark.asyncio
    async def test_missing_credential_type_relationship_fails(self) -> None:
        """A credential whose credential_type relationship is None fails type validation."""
        project_id = uuid4()
        cred_id = uuid4()
        cred = _make_credential_mock(cred_id=cred_id, project_id=project_id)
        cred.credential_type = None

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [cred]
        mock_session.exec = AsyncMock(return_value=mock_result)

        executor = _make_executor(mock_session)
        meta = InvocationMetadata(
            integration_connections=[
                IntegrationConnectionConfig(integration_id=str(uuid4()), credential_id=str(cred_id))
            ],
        )

        with pytest.raises(CredentialResolutionError, match="unknown"):
            await executor._validate_credentials_eagerly(meta, project_id)


class TestInitOrchestrationEagerValidation:
    """Tests that _init_orchestration calls eager validation and handles failures."""

    @pytest.mark.asyncio
    async def test_credential_resolution_error_marks_invocation_failed(self) -> None:
        """CredentialResolutionError from eager validation returns None and marks invocation FAILED."""
        executor = _make_executor()

        bad_cred_id = str(uuid4())
        ctx = InvocationContextData.model_validate(
            {
                "metadata": {
                    "integration_connections": [
                        {
                            "integration_id": str(uuid4()),
                            "credential_id": bad_cred_id,
                        }
                    ],
                }
            }
        )

        invocation = MagicMock()
        invocation.id = uuid4()
        invocation.project_id = uuid4()

        with patch.object(
            executor,
            "_validate_credentials_eagerly",
            new_callable=AsyncMock,
            side_effect=CredentialResolutionError(f"Credential '{bad_cred_id}' not found."),
        ):
            with patch.object(executor, "_update_invocation_status", new_callable=AsyncMock) as mock_update:
                with patch.object(
                    type(executor),
                    "_WorkflowSignalClient",
                    create=True,
                ):
                    with patch(
                        "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient"
                    ) as mock_signal:
                        mock_signal.send_failure_signal = AsyncMock()
                        result = await executor._init_orchestration(invocation, ctx)

        assert result is None
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][1] == InvocationStatus.FAILED
