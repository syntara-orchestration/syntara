"""Tests for SSRF protection in integration configuration schemas."""

from unittest.mock import patch

import pytest

from syntara.integrations.models.integration_configuration import (
    AAPConfiguration,
    LLMProviderConfiguration,
    LLMProviderHint,
    MCPServerConfigurationInput,
)


def _mock_getaddrinfo(ip: str) -> list[tuple[None, None, None, None, tuple[str, int]]]:
    """Return a mock getaddrinfo result for a given IP."""
    return [(None, None, None, None, (ip, 0))]


_PATCH_GETADDRINFO = "socket.getaddrinfo"
_PUBLIC_IP = "93.184.216.34"


class TestAAPConfigurationSSRF:
    """Tests for SSRF protection in AAPConfiguration schema validation."""

    def test_cloud_metadata_ipv4_rejected(self) -> None:
        """Reject AWS/GCP cloud metadata endpoint IPv4."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            AAPConfiguration(
                base_url="http://169.254.169.254",
                allow_http=True,
            )

    def test_cloud_metadata_ipv6_rejected(self) -> None:
        """Reject AWS IPv6 cloud metadata endpoint."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            AAPConfiguration(
                base_url="http://[fd00:ec2::254]",
                allow_http=True,
            )

    def test_kubernetes_internal_dns_rejected(self) -> None:
        """Reject Kubernetes internal service DNS resolving to a private IP."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            AAPConfiguration(
                base_url="http://kubernetes.default.svc",
                allow_http=True,
            )

    def test_private_ip_rejected(self) -> None:
        """Reject RFC1918 private IP without allowlist."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            AAPConfiguration(
                base_url="http://192.168.1.100",
                allow_http=True,
            )

    def test_public_url_accepted(self) -> None:
        """Accept public URL resolving to a public IP."""
        with patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo(_PUBLIC_IP)):
            config = AAPConfiguration(base_url="https://aap.example.com")
        assert config.base_url == "https://aap.example.com"


class TestMCPConfigurationSSRF:
    """Tests for SSRF protection in MCPServerConfigurationInput schema validation."""

    def test_cloud_metadata_rejected(self) -> None:
        """Reject cloud metadata endpoint."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            MCPServerConfigurationInput(
                base_url="http://169.254.169.254/mcp",
                allow_http=True,
            )

    def test_public_url_accepted(self) -> None:
        """Accept public URL with path resolving to a public IP."""
        with patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo(_PUBLIC_IP)):
            config = MCPServerConfigurationInput(base_url="https://mcp.example.com/mcp")
        assert config.base_url == "https://mcp.example.com/mcp"


class TestLLMProviderConfigurationSSRF:
    """Tests for SSRF protection in LLMProviderConfiguration schema validation."""

    def test_cloud_metadata_rejected_red_hat_ai(self) -> None:
        """Reject cloud metadata for red_hat_ai provider."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            LLMProviderConfiguration(
                provider_hint=LLMProviderHint.RED_HAT_AI,
                base_url="http://169.254.169.254",
                allow_http=True,
            )

    def test_cloud_metadata_rejected_custom(self) -> None:
        """Reject cloud metadata for custom provider."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            LLMProviderConfiguration(
                provider_hint=LLMProviderHint.CUSTOM,
                base_url="http://169.254.169.254",
                allow_http=True,
            )

    def test_public_url_accepted(self) -> None:
        """Accept public URL for red_hat_ai resolving to a public IP."""
        with patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo(_PUBLIC_IP)):
            config = LLMProviderConfiguration(
                provider_hint=LLMProviderHint.RED_HAT_AI,
                base_url="https://llm.example.com",
            )
        assert config.base_url == "https://llm.example.com"
