"""Tests for integrations/lib/url_validation.validate_integration_url_no_ssrf()."""

from unittest.mock import patch

import pytest

from syntara.integrations.lib.url_validation import (
    validate_integration_configuration_no_ssrf,
    validate_integration_url_no_ssrf,
)


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

    def test_localhost_accepted_when_allowlisted_and_allow_http_false(self) -> None:
        """Accept allowlisted loopback over HTTP even when allow_http is False.

        Mirrors the scheme layer, which always permits loopback over HTTP: the documented
        ``make dev`` path (allowlist localhost for a local MCP server on 127.0.0.1:8765)
        uses http://localhost with the default allow_http=False and must not be rejected
        here after passing the scheme validator.
        """
        with patch(_PATCH_GET_SETTINGS, return_value=_settings(["localhost"])):
            validate_integration_url_no_ssrf("http://localhost:8765", allow_http=False)

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


class TestValidateConfigurationNoSsrf:
    """Tests for validate_integration_configuration_no_ssrf() — the shared choke point."""

    def test_missing_base_url_attribute_is_noop(self) -> None:
        """A configuration without a base_url attribute is a no-op (must not raise)."""
        config = type("C", (), {})()  # no base_url attribute
        validate_integration_configuration_no_ssrf(config)

    def test_none_base_url_is_noop(self) -> None:
        """A None base_url (e.g. an LLM provider using its default endpoint) is a no-op."""
        config = type("C", (), {"base_url": None})()
        validate_integration_configuration_no_ssrf(config)

    def test_empty_base_url_is_noop(self) -> None:
        """An empty base_url is a no-op."""
        config = type("C", (), {"base_url": ""})()
        validate_integration_configuration_no_ssrf(config)

    @pytest.mark.ssrf_enforced
    def test_present_base_url_is_validated_and_allow_http_forwarded(self) -> None:
        """A present base_url is routed through the real check, forwarding the allow_http flag.

        Confirms the choke point is not a blanket no-op: it reads base_url and the per-config
        allow_http flag and delegates to validate_integration_url_no_ssrf. Marked
        ``ssrf_enforced`` so the autouse bypass does not intercept the delegated call.
        """
        # allow_http=False: http:// to a public IP is rejected (https required by default).
        blocked = type("C", (), {"base_url": f"http://{_PUBLIC_IP}", "allow_http": False})()
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_integration_configuration_no_ssrf(blocked)

        # allow_http=True: the same URL is accepted, proving the flag reached the validator.
        allowed = type("C", (), {"base_url": f"http://{_PUBLIC_IP}", "allow_http": True})()
        validate_integration_configuration_no_ssrf(allowed)
