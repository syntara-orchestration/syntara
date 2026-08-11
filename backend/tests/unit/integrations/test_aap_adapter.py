"""Tests for the Ansible Automation Platform adapter — validate() and discover() methods."""

from __future__ import annotations

import logging
import ssl
import unittest.mock
from typing import Any

import httpx
import pytest
import respx
from httpx import Response

from syntara.integrations.adapters.aap import AAPAdapter
from syntara.integrations.adapters.protocol import (
    HealthCheckErrorType,
    IntegrationAdapter,
)
from syntara.integrations.models.integration_configuration import AAPConfiguration

_GATEWAY_URL = "https://aap.example.com"
_HEALTH_URL = f"{_GATEWAY_URL}/api/gateway/v1/me/"
_TEST_TOKEN = "test-token-value"  # noqa: S105
_TEST_USERNAME = "admin"
_TEST_PASSWORD = "secret-password"  # noqa: S105


@pytest.fixture
def aap_config() -> AAPConfiguration:
    """Create a test Ansible Automation Platform configuration."""
    return AAPConfiguration(
        base_url=_GATEWAY_URL,
        insecure_skip_tls_verify=False,
    )


@pytest.fixture
def resolved_credential() -> dict[str, Any]:
    """Standard resolved credential with a valid OAuth token.

    Mirrors the full InjectorResolver.resolve() output shape for the
    "Ansible Automation Platform" credential type. Keys like aap_host and
    aap_verify_ssl are unused by the adapter (URL and TLS config come from
    AAPConfiguration) but are included here to match the real extra_vars
    dict the adapter receives at runtime.
    """
    return {
        "auth_type": "aap",
        "aap_oauth_token": _TEST_TOKEN,
        "aap_username": "",
        "aap_password": "",
    }


class TestAAPAdapterProtocol:
    """Tests that AAPAdapter satisfies the adapter Protocol."""

    def test_is_instance_of_protocol(self, aap_config: AAPConfiguration) -> None:
        """Verify AAPAdapter implements IntegrationAdapter."""
        adapter = AAPAdapter(aap_config)
        assert isinstance(adapter, IntegrationAdapter)


class TestAAPValidateSuccess:
    """Tests for successful AAPAdapter.validate() calls."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_success(self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]) -> None:
        """200 from /me/ returns success=True."""
        respx.get(_HEALTH_URL).mock(return_value=Response(200, json={"results": [{"id": 1, "username": "admin"}]}))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is True
        assert result.error is None
        assert result.error_type is None
        assert result.checked_at is not None

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_sends_bearer_token(
        self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """Validate sends Authorization: Bearer header with the token."""
        route = respx.get(_HEALTH_URL).mock(return_value=Response(200, json={}))

        adapter = AAPAdapter(aap_config)
        await adapter.validate(resolved_credential, timeout_seconds=10)

        assert route.called
        request = route.calls.last.request
        assert request.headers["authorization"] == f"Bearer {_TEST_TOKEN}"


class TestAAPValidateBasicAuth:
    """Tests for username+password (Basic Auth) fallback path."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_basic_auth_success(self, aap_config: AAPConfiguration) -> None:
        """Falls back to Basic Auth when no oauth_token is present."""
        credential: dict[str, Any] = {
            "aap_oauth_token": "",
            "aap_username": _TEST_USERNAME,
            "aap_password": _TEST_PASSWORD,
        }
        respx.get(_HEALTH_URL).mock(return_value=Response(200, json={}))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(credential, timeout_seconds=10)

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_basic_auth_sends_authorization_header(self, aap_config: AAPConfiguration) -> None:
        """Basic Auth fallback sends correct Authorization header."""
        credential: dict[str, Any] = {
            "aap_oauth_token": "",
            "aap_username": _TEST_USERNAME,
            "aap_password": _TEST_PASSWORD,
        }
        route = respx.get(_HEALTH_URL).mock(return_value=Response(200, json={}))

        adapter = AAPAdapter(aap_config)
        await adapter.validate(credential, timeout_seconds=10)

        assert route.called
        request = route.calls.last.request
        assert "basic" in request.headers["authorization"].lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_oauth_token_takes_precedence(self, aap_config: AAPConfiguration) -> None:
        """When both oauth_token and username+password exist, Bearer token is used."""
        credential: dict[str, Any] = {
            "aap_oauth_token": _TEST_TOKEN,
            "aap_username": _TEST_USERNAME,
            "aap_password": _TEST_PASSWORD,
        }
        route = respx.get(_HEALTH_URL).mock(return_value=Response(200, json={}))

        adapter = AAPAdapter(aap_config)
        await adapter.validate(credential, timeout_seconds=10)

        assert route.called
        request = route.calls.last.request
        assert request.headers["authorization"] == f"Bearer {_TEST_TOKEN}"

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_basic_auth_401(self, aap_config: AAPConfiguration) -> None:
        """Basic Auth with bad credentials returns AUTH_FAILURE."""
        credential: dict[str, Any] = {
            "aap_oauth_token": "",
            "aap_username": "wrong",
            "aap_password": "bad",
        }
        respx.get(_HEALTH_URL).mock(return_value=Response(401))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE


class TestAAPValidateAuthErrors:
    """Tests for authentication-related failures."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_auth_failure_401(
        self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """HTTP 401 returns AUTH_FAILURE."""
        respx.get(_HEALTH_URL).mock(return_value=Response(401))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert "401" in (result.error or "")

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_auth_failure_403(
        self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """HTTP 403 returns AUTH_FAILURE."""
        respx.get(_HEALTH_URL).mock(return_value=Response(403))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_validate_no_credentials_at_all(self, aap_config: AAPConfiguration) -> None:
        """No token and no username/password returns AUTH_FAILURE without making a request."""
        credential_empty: dict[str, Any] = {
            "auth_type": "aap",
            "aap_username": "",
            "aap_password": "",
            "aap_oauth_token": "",
        }

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(credential_empty, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert "Authentication configuration is incomplete" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_missing_all_auth_keys(self, aap_config: AAPConfiguration) -> None:
        """Credential dict with no recognized auth keys returns AUTH_FAILURE."""
        credential_missing: dict[str, Any] = {"auth_type": "aap"}

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(credential_missing, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_validate_username_without_password(self, aap_config: AAPConfiguration) -> None:
        """Username present but no password (and no token) returns AUTH_FAILURE."""
        credential: dict[str, Any] = {
            "aap_oauth_token": "",
            "aap_username": "admin",
            "aap_password": "",
        }

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE

    @pytest.mark.asyncio
    @pytest.mark.parametrize("whitespace_token", [" ", "\t", "\n", "  \n\t  "])
    async def test_validate_whitespace_only_token(self, aap_config: AAPConfiguration, whitespace_token: str) -> None:
        """Whitespace-only tokens are treated as missing, not sent to the server."""
        credential: dict[str, Any] = {
            "aap_oauth_token": whitespace_token,
            "aap_username": "",
            "aap_password": "",
        }

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert "Authentication configuration is incomplete" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_whitespace_only_username_password(self, aap_config: AAPConfiguration) -> None:
        """Whitespace-only username/password are treated as missing."""
        credential: dict[str, Any] = {
            "aap_oauth_token": "",
            "aap_username": "  ",
            "aap_password": "\t",
        }

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE


class TestAAPValidateConnectionErrors:
    """Tests for connection and server error scenarios."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_server_error_500(
        self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """HTTP 500 returns CONNECTION_ERROR, not AUTH_FAILURE."""
        respx.get(_HEALTH_URL).mock(return_value=Response(500))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert "500" in (result.error or "")

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_server_error_502(
        self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """HTTP 502 returns CONNECTION_ERROR."""
        respx.get(_HEALTH_URL).mock(return_value=Response(502))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_server_error_503(
        self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """HTTP 503 returns CONNECTION_ERROR."""
        respx.get(_HEALTH_URL).mock(return_value=Response(503))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_connection_error(
        self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """ConnectError (gateway unreachable) returns CONNECTION_ERROR."""
        respx.get(_HEALTH_URL).mock(side_effect=httpx.ConnectError("Connection refused"))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert result.error == "Unable to connect to Ansible Automation Platform"

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_timeout(self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]) -> None:
        """Timeout returns TIMEOUT error type."""
        respx.get(_HEALTH_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(resolved_credential, timeout_seconds=5)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.TIMEOUT
        assert "5s" in (result.error or "")

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_ssl_error(self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]) -> None:
        """SSL verification failure returns SSL_ERROR."""
        respx.get(_HEALTH_URL).mock(side_effect=ssl.SSLCertVerificationError("certificate verify failed"))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.SSL_ERROR
        assert result.error == "SSL/TLS verification failed"

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_unexpected_error(
        self,
        aap_config: AAPConfiguration,
        resolved_credential: dict[str, Any],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unexpected exceptions return CONNECTION_ERROR and never raise."""
        respx.get(_HEALTH_URL).mock(side_effect=RuntimeError("something bizarre"))

        adapter = AAPAdapter(aap_config)
        with caplog.at_level(logging.ERROR, logger="syntara.integrations.adapters.aap"):
            result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert result.error == "Request failed unexpectedly"
        assert any("Unexpected error" in r.message for r in caplog.records)


class TestAAPValidateTLSConfig:
    """Tests for insecure_skip_tls_verify configuration."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_insecure_skip_tls_passes_verify_false(self, resolved_credential: dict[str, Any]) -> None:
        """insecure_skip_tls_verify=True passes verify=False to httpx.AsyncClient."""
        config = AAPConfiguration(
            base_url=_GATEWAY_URL,
            insecure_skip_tls_verify=True,
        )
        respx.get(_HEALTH_URL).mock(return_value=Response(200, json={}))

        with unittest.mock.patch(
            "syntara.integrations.adapters.aap.httpx.AsyncClient", wraps=httpx.AsyncClient
        ) as mock_client:
            adapter = AAPAdapter(config)
            result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is True
        mock_client.assert_called_once()
        call_kwargs = mock_client.call_args[1]
        assert call_kwargs["verify"] is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_default_tls_passes_verify_true(self, resolved_credential: dict[str, Any]) -> None:
        """insecure_skip_tls_verify=False (default) passes verify=True to httpx.AsyncClient."""
        config = AAPConfiguration(
            base_url=_GATEWAY_URL,
            insecure_skip_tls_verify=False,
        )
        respx.get(_HEALTH_URL).mock(return_value=Response(200, json={}))

        with unittest.mock.patch(
            "syntara.integrations.adapters.aap.httpx.AsyncClient", wraps=httpx.AsyncClient
        ) as mock_client:
            adapter = AAPAdapter(config)
            result = await adapter.validate(resolved_credential, timeout_seconds=10)

        assert result.success is True
        mock_client.assert_called_once()
        call_kwargs = mock_client.call_args[1]
        assert call_kwargs["verify"] is True


class TestAAPValidateSanitization:
    """Tests that error messages and logs don't leak sensitive information."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_credential_not_leaked_in_error(self, aap_config: AAPConfiguration) -> None:
        """Token value never appears in result.error."""
        secret_token = "SUPER-SECRET-AAP-TOKEN-XYZ"  # noqa: S105
        credential: dict[str, Any] = {"aap_oauth_token": secret_token}

        respx.get(_HEALTH_URL).mock(return_value=Response(401))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(credential, timeout_seconds=10)

        assert secret_token not in (result.error or "")

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_credential_not_leaked_in_logs(
        self,
        aap_config: AAPConfiguration,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Token value never appears in log output."""
        secret_token = "SUPER-SECRET-AAP-TOKEN-999"  # noqa: S105
        credential: dict[str, Any] = {"aap_oauth_token": secret_token}

        respx.get(_HEALTH_URL).mock(side_effect=httpx.ConnectError("Connection refused"))

        adapter = AAPAdapter(aap_config)
        with caplog.at_level(logging.DEBUG, logger="syntara.integrations.adapters.aap"):
            await adapter.validate(credential, timeout_seconds=10)

        assert secret_token not in caplog.text

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_password_not_leaked_in_error(self, aap_config: AAPConfiguration) -> None:
        """Password value never appears in result.error when using basic auth."""
        secret_password = "SUPER-SECRET-PASSWORD-XYZ"  # noqa: S105
        credential: dict[str, Any] = {
            "aap_oauth_token": "",
            "aap_username": "admin",
            "aap_password": secret_password,
        }

        respx.get(_HEALTH_URL).mock(return_value=Response(401))

        adapter = AAPAdapter(aap_config)
        result = await adapter.validate(credential, timeout_seconds=10)

        assert secret_password not in (result.error or "")


class TestAAPDiscover:
    """Tests for AAPAdapter.discover() — delegates to validate()."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_discover_delegates_to_validate(
        self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """discover() returns DiscoverResult with no resources on success."""
        respx.get(_HEALTH_URL).mock(return_value=Response(200, json={"results": [{"id": 1, "username": "admin"}]}))

        adapter = AAPAdapter(aap_config)
        result = await adapter.discover(resolved_credential, timeout_seconds=10)

        assert result.success is True
        assert result.discovered_tools is None
        assert result.discovered_models is None
        assert result.error is None
        assert result.checked_at is not None

    @pytest.mark.asyncio
    @respx.mock
    async def test_discover_propagates_errors(
        self, aap_config: AAPConfiguration, resolved_credential: dict[str, Any]
    ) -> None:
        """discover() returns failure when validate() fails."""
        respx.get(_HEALTH_URL).mock(return_value=Response(401))

        adapter = AAPAdapter(aap_config)
        result = await adapter.discover(resolved_credential, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert result.discovered_tools is None
        assert result.discovered_models is None
