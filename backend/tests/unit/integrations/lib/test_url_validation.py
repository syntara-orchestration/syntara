"""Tests for integrations/lib/url_validation.validate_integration_url_no_ssrf()."""

from unittest.mock import patch

import pytest

from syntara.integrations.lib.url_validation import validate_integration_url_no_ssrf


def _mock_getaddrinfo(ip: str) -> list[tuple[None, None, None, None, tuple[str, int]]]:
    """Return a mock getaddrinfo result for a given IP."""
    return [(None, None, None, None, (ip, 0))]


_PATCH_GETADDRINFO = "socket.getaddrinfo"
_PATCH_GET_SETTINGS = "syntara.integrations.lib.url_validation.get_settings"
_PUBLIC_IP = "93.184.216.34"


def _settings(allowed: list[str]) -> object:
    """Build a fake settings object exposing integration_url_allowed_hosts."""
    return type("S", (), {"integration_url_allowed_hosts": allowed})()


class TestValidateUrlNoSsrf:
    """Tests for validate_integration_url_no_ssrf() — integration base_url SSRF checks."""

    def test_public_ip_accepted(self) -> None:
        """Accept URLs resolving to public IPs."""
        with patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo(_PUBLIC_IP)):
            validate_integration_url_no_ssrf("https://aap.example.com")

    def test_localhost_rejected_without_allowlist(self) -> None:
        """Reject localhost by default; loopback is opt-in via the allowlist (residual SSRF)."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_url_no_ssrf("http://localhost:8765", allow_http=True)

    def test_loopback_ipv4_rejected_without_allowlist(self) -> None:
        """Reject 127.0.0.0/8 loopback by default."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_url_no_ssrf("http://127.0.0.1:8080", allow_http=True)

    def test_loopback_ipv6_rejected_without_allowlist(self) -> None:
        """Reject ::1 loopback by default."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_url_no_ssrf("http://[::1]:8080", allow_http=True)

    def test_localhost_accepted_when_allowlisted(self) -> None:
        """Accept localhost only when explicitly opted in via integration_url_allowed_hosts."""
        with patch(_PATCH_GET_SETTINGS, return_value=_settings(["localhost"])):
            validate_integration_url_no_ssrf("http://localhost:8765", allow_http=True)

    def test_loopback_ipv4_accepted_when_allowlisted(self) -> None:
        """Accept 127.0.0.1 loopback when the host is allowlisted."""
        with patch(_PATCH_GET_SETTINGS, return_value=_settings(["127.0.0.1"])):
            validate_integration_url_no_ssrf("http://127.0.0.1:8080", allow_http=True)

    def test_cloud_metadata_ipv4_rejected(self) -> None:
        """Reject AWS/GCP cloud metadata endpoint."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_url_no_ssrf("http://169.254.169.254", allow_http=True)

    def test_cloud_metadata_ipv6_rejected(self) -> None:
        """Reject AWS IPv6 cloud metadata endpoint."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_url_no_ssrf("http://[fd00:ec2::254]", allow_http=True)

    def test_kubernetes_internal_dns_rejected(self) -> None:
        """Reject Kubernetes internal service DNS resolving to a private IP."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_integration_url_no_ssrf("http://kubernetes.default.svc", allow_http=True)

    def test_private_ip_rejected(self) -> None:
        """Reject RFC1918 private IP without allowlist."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_url_no_ssrf("http://192.168.1.100", allow_http=True)

    def test_https_required_by_default(self) -> None:
        """Reject http:// for a public host when allow_http is False."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo(_PUBLIC_IP)),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_integration_url_no_ssrf("http://aap.example.com")

    def test_allowlisted_private_host_accepted(self) -> None:
        """Accept a private IP when the hostname is in integration_url_allowed_hosts."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
            patch(_PATCH_GET_SETTINGS, return_value=_settings(["aap.internal.corp"])),
        ):
            validate_integration_url_no_ssrf("http://aap.internal.corp", allow_http=True)

    def test_allowlist_does_not_permit_cloud_metadata(self) -> None:
        """Cloud metadata is blocked even when the hostname is allowlisted."""
        with (
            patch(_PATCH_GET_SETTINGS, return_value=_settings(["169.254.169.254"])),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_integration_url_no_ssrf("http://169.254.169.254", allow_http=True)
