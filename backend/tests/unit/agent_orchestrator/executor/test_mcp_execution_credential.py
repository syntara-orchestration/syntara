"""Unit tests for InvocationExecutor._resolve_mcp_execution_credential.

Exercises the shared _resolve_credential method through the MCP execution
credential path, covering all error branches and the happy path.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.exceptions import CredentialResolutionError
from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor


def _make_executor(mock_session: MagicMock | None = None) -> tuple[InvocationExecutor, MagicMock]:
    """Build a minimal InvocationExecutor with a controllable mock session."""
    session = mock_session or MagicMock()

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[MagicMock, None]:
        yield session

    executor = InvocationExecutor.__new__(InvocationExecutor)
    executor.get_async_session_context = mock_session_ctx
    executor.session_factory = mock_session_ctx  # type: ignore[assignment]
    return executor, session


def _mock_credential_and_type(
    *,
    enabled: bool = True,
    has_secret: bool = True,
    has_cred_type: bool = True,
) -> tuple[MagicMock, MagicMock | None]:
    """Create mock Credential and CredentialType for session.get dispatch."""
    mock_credential = MagicMock()
    mock_credential.enabled = enabled
    mock_credential.secret_id = uuid4() if has_secret else None
    mock_credential.credential_type_id = uuid4()

    mock_cred_type = MagicMock() if has_cred_type else None
    if mock_cred_type:
        mock_cred_type.injectors = {}

    return mock_credential, mock_cred_type


def _session_get_dispatch(mock_credential: MagicMock, mock_cred_type: MagicMock | None) -> AsyncMock:
    """Build a session.get side_effect that dispatches by model class."""

    async def _get(model_class: type, pk: object) -> object | None:
        from syntara.credentials.models.credential import Credential
        from syntara.credentials.models.credential_type import CredentialType

        if model_class is Credential:
            return mock_credential
        if model_class is CredentialType:
            return mock_cred_type
        return None

    return AsyncMock(side_effect=_get)


class TestResolveMcpExecutionCredential:
    """Tests for _resolve_mcp_execution_credential exercising _resolve_credential."""

    @pytest.mark.asyncio
    async def test_happy_path_with_bearer_token(self) -> None:
        executor, session = _make_executor()
        mock_credential, mock_cred_type = _mock_credential_and_type()
        session.get = _session_get_dispatch(mock_credential, mock_cred_type)

        mock_resolved = MagicMock()
        mock_resolved.extra_vars = {"bearer_token": "tok-abc-123"}

        with (
            patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc,
            patch("syntara.agent_orchestrator.executor.invocation_executor.InjectorResolver") as mock_injector,
        ):
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(return_value={"token": "encrypted"})
            mock_injector.resolve.return_value = mock_resolved

            result = await executor._resolve_mcp_execution_credential(str(uuid4()))

        assert result == "tok-abc-123"

    @pytest.mark.asyncio
    async def test_happy_path_no_bearer_token(self) -> None:
        executor, session = _make_executor()
        mock_credential, mock_cred_type = _mock_credential_and_type()
        session.get = _session_get_dispatch(mock_credential, mock_cred_type)

        mock_resolved = MagicMock()
        mock_resolved.extra_vars = {}

        with (
            patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc,
            patch("syntara.agent_orchestrator.executor.invocation_executor.InjectorResolver") as mock_injector,
        ):
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(return_value={"token": "encrypted"})
            mock_injector.resolve.return_value = mock_resolved

            result = await executor._resolve_mcp_execution_credential(str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_uuid(self) -> None:
        executor, _ = _make_executor()

        with pytest.raises(CredentialResolutionError, match="Invalid execution credential ID"):
            await executor._resolve_mcp_execution_credential("not-a-uuid")

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        executor, session = _make_executor()
        session.get = AsyncMock(return_value=None)
        cred_id = str(uuid4())

        with pytest.raises(CredentialResolutionError, match="not found"):
            await executor._resolve_mcp_execution_credential(cred_id)

    @pytest.mark.asyncio
    async def test_disabled(self) -> None:
        executor, session = _make_executor()
        mock_credential, _ = _mock_credential_and_type(enabled=False)
        session.get = AsyncMock(return_value=mock_credential)
        cred_id = str(uuid4())

        with pytest.raises(CredentialResolutionError, match="disabled"):
            await executor._resolve_mcp_execution_credential(cred_id)

    @pytest.mark.asyncio
    async def test_no_secret_id(self) -> None:
        executor, session = _make_executor()
        mock_credential, _ = _mock_credential_and_type(has_secret=False)
        session.get = AsyncMock(return_value=mock_credential)
        cred_id = str(uuid4())

        with pytest.raises(CredentialResolutionError, match="no stored secret"):
            await executor._resolve_mcp_execution_credential(cred_id)

    @pytest.mark.asyncio
    async def test_decryption_failure(self) -> None:
        executor, session = _make_executor()
        mock_credential, _ = _mock_credential_and_type()
        session.get = AsyncMock(return_value=mock_credential)
        cred_id = str(uuid4())

        with patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc:
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(side_effect=RuntimeError("decrypt failed"))

            with pytest.raises(CredentialResolutionError, match="Failed to decrypt"):
                await executor._resolve_mcp_execution_credential(cred_id)

    @pytest.mark.asyncio
    async def test_credential_type_not_found(self) -> None:
        executor, session = _make_executor()
        mock_credential, _ = _mock_credential_and_type(has_cred_type=False)

        async def mock_get(model_class: type, pk: object) -> object | None:
            from syntara.credentials.models.credential import Credential

            if model_class is Credential:
                return mock_credential
            return None

        session.get = AsyncMock(side_effect=mock_get)
        cred_id = str(uuid4())

        with patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc:
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(return_value={"token": "encrypted"})

            with pytest.raises(CredentialResolutionError, match="Credential type for"):
                await executor._resolve_mcp_execution_credential(cred_id)

    @pytest.mark.asyncio
    async def test_injector_resolution_failure(self) -> None:
        executor, session = _make_executor()
        mock_credential, mock_cred_type = _mock_credential_and_type()
        session.get = _session_get_dispatch(mock_credential, mock_cred_type)
        cred_id = str(uuid4())

        with (
            patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc,
            patch("syntara.agent_orchestrator.executor.invocation_executor.InjectorResolver") as mock_injector,
        ):
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(return_value={"token": "encrypted"})
            mock_injector.resolve.side_effect = RuntimeError("template error")

            with pytest.raises(CredentialResolutionError, match="Failed to resolve"):
                await executor._resolve_mcp_execution_credential(cred_id)
