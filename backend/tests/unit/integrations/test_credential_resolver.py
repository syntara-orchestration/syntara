"""Unit tests for the shared MCP credential resolver utility."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.credentials.exceptions import CredentialDisabledError
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError, IntegrationCredentialRequiredError
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type, resolve_mcp_bearer_token
from syntara.integrations.models.integration import IntegrationType


class TestFetchCredentialWithType:
    """Tests for fetch_credential_with_type."""

    @pytest.mark.asyncio
    async def test_raises_when_credential_not_found(self) -> None:
        credential_id = uuid4()
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        with pytest.raises(IntegrationCredentialNotFoundError):
            await fetch_credential_with_type(session, credential_id)

    @pytest.mark.asyncio
    async def test_raises_when_secret_id_missing_and_require_secret_true(self) -> None:
        credential_id = uuid4()
        credential = MagicMock()
        credential.secret_id = None

        session = AsyncMock()
        session.get = AsyncMock(return_value=credential)

        with pytest.raises(IntegrationCredentialNotFoundError):
            await fetch_credential_with_type(session, credential_id)

    @pytest.mark.asyncio
    async def test_passes_when_secret_id_missing_and_require_secret_false(self) -> None:
        credential_id = uuid4()
        cred_type_id = uuid4()

        credential = MagicMock()
        credential.secret_id = None
        credential.credential_type_id = cred_type_id

        cred_type = MagicMock()

        session = AsyncMock()
        session.get = AsyncMock(side_effect=[credential, cred_type])

        result_cred, result_type = await fetch_credential_with_type(session, credential_id, require_secret=False)

        assert result_cred is credential
        assert result_type is cred_type

    @pytest.mark.asyncio
    async def test_raises_when_credential_type_not_found(self) -> None:
        credential_id = uuid4()
        credential = MagicMock()
        credential.secret_id = uuid4()
        credential.credential_type_id = uuid4()

        session = AsyncMock()
        session.get = AsyncMock(side_effect=[credential, None])

        with pytest.raises(IntegrationCredentialNotFoundError):
            await fetch_credential_with_type(session, credential_id)

    @pytest.mark.asyncio
    async def test_returns_credential_and_type_on_success(self) -> None:
        credential_id = uuid4()
        credential = MagicMock()
        credential.secret_id = uuid4()
        credential.credential_type_id = uuid4()

        cred_type = MagicMock()

        session = AsyncMock()
        session.get = AsyncMock(side_effect=[credential, cred_type])

        result_cred, result_type = await fetch_credential_with_type(session, credential_id)

        assert result_cred is credential
        assert result_type is cred_type

    @pytest.mark.asyncio
    async def test_returns_disabled_credential_without_raising(self) -> None:
        """Disabled credentials are intentionally allowed through fetch_credential_with_type."""
        credential_id = uuid4()
        credential = MagicMock()
        credential.secret_id = uuid4()
        credential.credential_type_id = uuid4()
        credential.enabled = False

        cred_type = MagicMock()

        session = AsyncMock()
        session.get = AsyncMock(side_effect=[credential, cred_type])

        result_cred, result_type = await fetch_credential_with_type(session, credential_id)

        assert result_cred is credential
        assert result_cred.enabled is False
        assert result_type is cred_type


class TestResolveMcpBearerToken:
    """Tests for resolve_mcp_bearer_token."""

    @pytest.mark.asyncio
    async def test_raises_when_integration_not_found(self) -> None:
        """Raises IntegrationCredentialRequiredError when integration_id does not exist."""
        integration_id = uuid4()
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        secret_service = MagicMock()

        with pytest.raises(IntegrationCredentialRequiredError):
            await resolve_mcp_bearer_token(session, secret_service, integration_id)

        secret_service.retrieve_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_no_management_credential(self) -> None:
        """Raises IntegrationCredentialRequiredError when the integration has no credential."""
        integration_id = uuid4()
        integration = MagicMock()
        integration.management_credential_id = None

        session = AsyncMock()
        session.get = AsyncMock(return_value=integration)
        secret_service = MagicMock()

        with pytest.raises(IntegrationCredentialRequiredError):
            await resolve_mcp_bearer_token(session, secret_service, integration_id)

    @pytest.mark.asyncio
    async def test_raises_when_credential_not_found(self) -> None:
        """Raises IntegrationCredentialNotFoundError when the Credential record is missing."""
        integration_id = uuid4()
        credential_id = uuid4()

        integration = MagicMock()
        integration.management_credential_id = credential_id

        session = AsyncMock()
        session.get = AsyncMock(side_effect=[integration, None])
        secret_service = MagicMock()

        with pytest.raises(IntegrationCredentialNotFoundError):
            await resolve_mcp_bearer_token(session, secret_service, integration_id)

    @pytest.mark.asyncio
    async def test_raises_when_bearer_token_missing_from_injectors(self) -> None:
        """Raises IntegrationCredentialRequiredError when resolved injectors have no bearer_token."""
        integration_id = uuid4()
        credential_id = uuid4()
        secret_id = uuid4()
        cred_type_id = uuid4()

        integration = MagicMock()
        integration.id = integration_id
        integration.management_credential_id = credential_id

        credential = MagicMock()
        credential.secret_id = secret_id
        credential.credential_type_id = cred_type_id

        cred_type = MagicMock()
        cred_type.injectors = {}

        session = AsyncMock()
        session.get = AsyncMock(side_effect=[integration, credential, cred_type])

        secret_service = MagicMock()
        secret_service.retrieve_secret = AsyncMock(return_value={})

        with pytest.raises(IntegrationCredentialRequiredError):
            await resolve_mcp_bearer_token(session, secret_service, integration_id)

    @pytest.mark.asyncio
    async def test_returns_bearer_token_on_success(self) -> None:
        """Returns the bearer_token string when all lookups succeed."""
        integration_id = uuid4()
        credential_id = uuid4()
        secret_id = uuid4()
        cred_type_id = uuid4()

        integration = MagicMock()
        integration.id = integration_id
        integration.integration_type = IntegrationType.MCP_SERVER
        integration.management_credential_id = credential_id

        credential = MagicMock()
        credential.secret_id = secret_id
        credential.credential_type_id = cred_type_id

        cred_type = MagicMock()
        cred_type.injectors = {"extra_vars": {"bearer_token": "{{token}}"}}

        session = AsyncMock()
        session.get = AsyncMock(side_effect=[integration, credential, cred_type])

        secret_service = MagicMock()
        secret_service.retrieve_secret = AsyncMock(return_value={"token": "my-secret-token"})

        result = await resolve_mcp_bearer_token(session, secret_service, integration_id)

        assert result == "my-secret-token"
        secret_service.retrieve_secret.assert_awaited_once_with(secret_id)

    @pytest.mark.asyncio
    async def test_raises_when_credential_disabled(self) -> None:
        """Raises CredentialDisabledError when the credential is disabled."""
        integration_id = uuid4()
        credential_id = uuid4()
        cred_type_id = uuid4()

        integration = MagicMock()
        integration.id = integration_id
        integration.management_credential_id = credential_id

        credential = MagicMock()
        credential.secret_id = uuid4()
        credential.credential_type_id = cred_type_id
        credential.enabled = False
        credential.name = "Disabled MCP Cred"

        cred_type = MagicMock()

        session = AsyncMock()
        session.get = AsyncMock(side_effect=[integration, credential, cred_type])

        secret_service = MagicMock()

        with pytest.raises(CredentialDisabledError):
            await resolve_mcp_bearer_token(session, secret_service, integration_id)

        secret_service.retrieve_secret.assert_not_called()
