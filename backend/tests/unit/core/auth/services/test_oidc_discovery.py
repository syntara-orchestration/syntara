"""Unit tests for OIDC discovery service."""

from unittest.mock import AsyncMock, patch

import pytest

from syntara.identity_providers.services.oidc_discovery import CLAIM_ALIASES, OIDCTestResult
from syntara.identity_providers.services.oidc_discovery import test_oidc_connection as run_oidc_connection_test


class TestOIDCTestResult:
    """Tests for OIDCTestResult model."""

    def test_includes_claims_supported_and_aliases(self) -> None:
        """Test that OIDCTestResult can carry claims_supported and claim_aliases."""
        result = OIDCTestResult(
            success=True,
            message="ok",
            claims_supported=["sub", "email", "name"],
            claim_aliases=CLAIM_ALIASES,
        )
        assert result.claims_supported == ["sub", "email", "name"]
        assert result.claim_aliases is not None
        assert "email" in result.claim_aliases
        assert result.end_session_endpoint_supported is False

    def test_defaults_to_none(self) -> None:
        """Test that claims_supported and claim_aliases default to None."""
        result = OIDCTestResult(success=False, message="fail")
        assert result.claims_supported is None
        assert result.claim_aliases is None
        assert result.end_session_endpoint_supported is False


class TestTestOIDCConnection:
    """Tests for run_oidc_connection_test function."""

    @pytest.mark.asyncio
    async def test_success_returns_claims_supported_and_aliases(self) -> None:
        """Test that successful connection returns claims_supported and claim_aliases."""
        discovery_data = {
            "issuer": "https://idp.example.com",
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "jwks_uri": "https://idp.example.com/jwks",
            "claims_supported": ["sub", "email", "name", "preferred_username", "groups"],
            "end_session_endpoint": "https://idp.example.com/logout",
        }

        with patch("syntara.identity_providers.services.oidc_discovery.OIDCService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.fetch_discovery_config = AsyncMock(return_value=discovery_data)

            result = await run_oidc_connection_test("https://idp.example.com")

        assert result.success is True
        assert result.claims_supported == ["sub", "email", "name", "preferred_username", "groups"]
        assert result.claim_aliases == CLAIM_ALIASES
        assert result.end_session_endpoint_supported is True

    @pytest.mark.asyncio
    async def test_success_without_claims_supported(self) -> None:
        """Test that claims_supported is None when not in discovery response."""
        discovery_data = {
            "issuer": "https://idp.example.com",
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "jwks_uri": "https://idp.example.com/jwks",
        }

        with patch("syntara.identity_providers.services.oidc_discovery.OIDCService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.fetch_discovery_config = AsyncMock(return_value=discovery_data)

            result = await run_oidc_connection_test("https://idp.example.com")

        assert result.success is True
        assert result.claims_supported is None
        assert result.claim_aliases == CLAIM_ALIASES
        assert result.end_session_endpoint_supported is False

    @pytest.mark.asyncio
    async def test_disable_tls_verify_passed_to_oidc_service(self) -> None:
        """Test that disable_tls_verify flag is forwarded to OIDCService."""
        discovery_data = {
            "issuer": "https://idp.example.com",
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "jwks_uri": "https://idp.example.com/jwks",
        }

        with patch("syntara.identity_providers.services.oidc_discovery.OIDCService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.fetch_discovery_config = AsyncMock(return_value=discovery_data)

            await run_oidc_connection_test("https://idp.example.com", disable_tls_verify=True)

            mock_svc.fetch_discovery_config.assert_called_once_with("https://idp.example.com", disable_tls_verify=True)

    @pytest.mark.asyncio
    async def test_failure_has_no_claims_data(self) -> None:
        """Test that failed connection has no claims_supported or claim_aliases."""
        from syntara.auth.services.oidc_service import OIDCError

        with patch("syntara.identity_providers.services.oidc_discovery.OIDCService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.fetch_discovery_config = AsyncMock(side_effect=OIDCError("Connection refused"))

            result = await run_oidc_connection_test("https://bad.example.com")

        assert result.success is False
        assert result.claims_supported is None
        assert result.claim_aliases is None
        assert result.end_session_endpoint_supported is False
