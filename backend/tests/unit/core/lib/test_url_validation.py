"""Tests for URL validation utilities (SSRF prevention)."""

from unittest.mock import patch

import pytest

from syntara.core.lib.url_validation import validate_endpoint_url, validate_host_url, validate_url_no_ssrf


class TestValidateHostUrl:
    """Tests for validate_host_url()."""

    def test_valid_https_host(self) -> None:
        """Accept a standard HTTPS host URL."""
        assert validate_host_url("https://controller.example.com") == "https://controller.example.com"

    def test_valid_https_host_with_port(self) -> None:
        """Accept HTTPS host with non-default port."""
        assert validate_host_url("https://controller.example.com:8443") == "https://controller.example.com:8443"

    def test_trailing_slash_normalized(self) -> None:
        """Accept trailing slash and normalize it away."""
        assert validate_host_url("https://controller.example.com/") == "https://controller.example.com"

    def test_default_port_omitted(self) -> None:
        """Omit default port (443 for HTTPS) from normalized output."""
        assert validate_host_url("https://controller.example.com:443") == "https://controller.example.com"

    def test_http_rejected_by_default(self) -> None:
        """Reject HTTP scheme when allow_http is False."""
        with pytest.raises(ValueError, match="scheme must be https"):
            validate_host_url("http://controller.example.com")

    def test_http_accepted_when_allowed(self) -> None:
        """Accept HTTP scheme when allow_http is True."""
        assert validate_host_url("http://controller.example.com", allow_http=True) == "http://controller.example.com"

    def test_http_default_port_omitted(self) -> None:
        """Omit default port (80 for HTTP) from normalized output."""
        result = validate_host_url("http://controller.example.com:80", allow_http=True)
        assert result == "http://controller.example.com"

    def test_path_injection_rejected(self) -> None:
        """Reject URLs with path components (SSRF vector)."""
        with pytest.raises(ValueError, match="must not contain a path"):
            validate_host_url("https://controller.example.com/foo/bar/")

    def test_query_suffix_attack_rejected(self) -> None:
        """Reject the specific ?-suffix attack from AAP-74616."""
        with pytest.raises(ValueError, match="must not contain a path"):
            validate_host_url("https://attacker.example.com/foo/bar/?")

    def test_query_string_rejected(self) -> None:
        """Reject URLs with query strings."""
        with pytest.raises(ValueError, match="must not contain a query string"):
            validate_host_url("https://controller.example.com?x=1")

    def test_fragment_rejected(self) -> None:
        """Reject URLs with fragments."""
        with pytest.raises(ValueError, match="must not contain a fragment"):
            validate_host_url("https://controller.example.com#frag")

    def test_ftp_scheme_rejected(self) -> None:
        """Reject non-HTTP(S) schemes."""
        with pytest.raises(ValueError, match="scheme must be https"):
            validate_host_url("ftp://controller.example.com")

    def test_file_scheme_rejected(self) -> None:
        """Reject file:// scheme (local file access)."""
        with pytest.raises(ValueError, match="scheme must be https"):
            validate_host_url("file:///etc/passwd")

    def test_empty_hostname_rejected(self) -> None:
        """Reject URLs with empty hostname."""
        with pytest.raises(ValueError, match="must include a hostname"):
            validate_host_url("https://")

    def test_empty_string_rejected(self) -> None:
        """Reject empty string."""
        with pytest.raises(ValueError, match="must not be empty"):
            validate_host_url("")

    def test_no_scheme_rejected(self) -> None:
        """Reject URLs without a scheme."""
        with pytest.raises(ValueError, match="must include a scheme"):
            validate_host_url("not-a-url")

    def test_backslash_userinfo_bypass_rejected(self) -> None:
        """Reject backslash in authority (urlparse misparses hostname)."""
        with pytest.raises(ValueError, match=r"userinfo.*backslash"):
            validate_host_url("https://host\\@evil.com")

    def test_at_sign_userinfo_rejected(self) -> None:
        """Reject @ in authority (userinfo injection)."""
        with pytest.raises(ValueError, match=r"userinfo.*backslash"):
            validate_host_url("https://user:pass@evil.com")

    def test_url_encoded_path_stays_in_hostname(self) -> None:
        """URL-encoded %2f stays in hostname (not decoded to path separator)."""
        result = validate_host_url("https://example.com%2ffoo")
        assert result == "https://example.com%2ffoo"

    def test_ipv4_address_accepted(self) -> None:
        """Accept IPv4 address as hostname."""
        assert validate_host_url("https://192.168.1.1") == "https://192.168.1.1"

    def test_ipv4_with_port_accepted(self) -> None:
        """Accept IPv4 address with non-default port."""
        assert validate_host_url("https://10.0.0.1:8443") == "https://10.0.0.1:8443"

    def test_ipv6_address_accepted(self) -> None:
        """Accept IPv6 address in bracket notation."""
        assert validate_host_url("https://[::1]") == "https://[::1]"

    def test_ipv6_with_port_accepted(self) -> None:
        """Accept IPv6 address with port, preserving RFC 3986 brackets."""
        assert validate_host_url("https://[2001:db8::1]:8443") == "https://[2001:db8::1]:8443"


class TestValidateEndpointUrl:
    """Tests for validate_endpoint_url() — allows paths, rejects query/fragment/userinfo."""

    def test_endpoint_with_path(self) -> None:
        """Accept endpoint URL with path (e.g., MCP servers at /mcp)."""
        assert validate_endpoint_url("http://localhost:8765/mcp", allow_http=True) == "http://localhost:8765/mcp"

    def test_endpoint_without_path(self) -> None:
        """Accept endpoint URL without path."""
        assert validate_endpoint_url("https://api.example.com", allow_http=False) == "https://api.example.com"

    def test_trailing_slash_preserved(self) -> None:
        """Trailing slash is preserved (not normalized away)."""
        assert validate_endpoint_url("http://localhost:8080/", allow_http=True) == "http://localhost:8080/"

    def test_nested_path_accepted(self) -> None:
        """Accept nested paths."""
        assert validate_endpoint_url("http://host:8000/api/v1/mcp", allow_http=True) == "http://host:8000/api/v1/mcp"

    def test_rejects_query_string(self) -> None:
        """Reject URLs with query strings."""
        with pytest.raises(ValueError, match="must not contain a query string"):
            validate_endpoint_url("http://localhost:8080/mcp?key=val", allow_http=True)

    def test_rejects_fragment(self) -> None:
        """Reject URLs with fragments."""
        with pytest.raises(ValueError, match="must not contain a fragment"):
            validate_endpoint_url("http://localhost:8080/mcp#section", allow_http=True)

    def test_rejects_userinfo(self) -> None:
        """Reject URLs with userinfo (@)."""
        with pytest.raises(ValueError, match="must not contain userinfo"):
            validate_endpoint_url("http://user:pass@localhost:8080/mcp", allow_http=True)

    def test_http_allowed_with_flag(self) -> None:
        """HTTP scheme accepted when allow_http=True."""
        assert validate_endpoint_url("http://localhost:8080", allow_http=True) == "http://localhost:8080"

    def test_http_rejected_by_default(self) -> None:
        """HTTP scheme rejected when allow_http=False (default) for non-loopback hosts."""
        with pytest.raises(ValueError, match="scheme must be"):
            validate_endpoint_url("http://remote.example.com:8080")

    def test_http_loopback_exemption_localhost(self) -> None:
        """HTTP allowed for localhost even when allow_http=False."""
        assert validate_endpoint_url("http://localhost:8080") == "http://localhost:8080"

    def test_http_loopback_exemption_127_range(self) -> None:
        """HTTP allowed for 127.x.x.x range even when allow_http=False."""
        assert validate_endpoint_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
        assert validate_endpoint_url("http://127.0.0.2:9090") == "http://127.0.0.2:9090"

    def test_http_loopback_exemption_ipv6(self) -> None:
        """HTTP allowed for ::1 even when allow_http=False."""
        assert validate_endpoint_url("http://[::1]:8080") == "http://[::1]:8080"

    def test_empty_url_rejected(self) -> None:
        """Empty URL is rejected."""
        with pytest.raises(ValueError, match="must not be empty"):
            validate_endpoint_url("")

    def test_missing_scheme_rejected(self) -> None:
        """URL without proper scheme is rejected."""
        with pytest.raises(ValueError, match="scheme must be"):
            validate_endpoint_url("localhost:8080")

    def test_missing_hostname_rejected(self) -> None:
        """URL without hostname is rejected."""
        with pytest.raises(ValueError, match="must include a hostname"):
            validate_endpoint_url("http:///path", allow_http=True)


def _mock_getaddrinfo(ip: str) -> list[tuple[None, None, None, None, tuple[str, int]]]:
    """Return a mock getaddrinfo result for a given IP."""
    return [(None, None, None, None, (ip, 0))]


_PATCH_GETADDRINFO = "socket.getaddrinfo"


class TestValidateUrlNoSsrf:
    """Tests for validate_url_no_ssrf() — hostname resolution SSRF checks."""

    def test_public_ip_accepted(self) -> None:
        """Accept URLs resolving to public IPs."""
        with patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("93.184.216.34")):
            validate_url_no_ssrf("https://example.com")

    def test_private_ip_10_rejected(self) -> None:
        """Reject 10.x.x.x private range."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("https://internal.example.com")

    def test_private_ip_172_rejected(self) -> None:
        """Reject 172.16.x.x private range."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("172.16.0.1")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("https://internal.example.com")

    def test_private_ip_192_rejected(self) -> None:
        """Reject 192.168.x.x private range."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("192.168.1.1")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("https://internal.example.com")

    def test_loopback_rejected(self) -> None:
        """Reject loopback address."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("127.0.0.1")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("http://localhost:8181")

    def test_ipv6_loopback_rejected(self) -> None:
        """Reject IPv6 loopback."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("::1")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("http://[::1]:8181")

    def test_link_local_rejected(self) -> None:
        """Reject link-local addresses."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("169.254.1.1")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("http://link-local.example.com")

    def test_cloud_metadata_ipv4_rejected(self) -> None:
        """Reject AWS/GCP cloud metadata endpoint."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_url_no_ssrf("http://169.254.169.254/latest/meta-data/")

    def test_cloud_metadata_ipv6_rejected(self) -> None:
        """Reject AWS IPv6 cloud metadata endpoint."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_url_no_ssrf("http://[fd00:ec2::254]/latest/meta-data/")

    def test_ftp_scheme_rejected(self) -> None:
        """Reject non-HTTP(S) schemes."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_url_no_ssrf("ftp://example.com")

    def test_file_scheme_rejected(self) -> None:
        """Reject file:// scheme."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_url_no_ssrf("file:///etc/passwd")

    def test_empty_url_rejected(self) -> None:
        """Reject empty URL."""
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_url_no_ssrf("")

    def test_unresolvable_host_rejected(self) -> None:
        """Reject URLs with unresolvable hostnames."""
        with pytest.raises(ValueError, match="resolve"):
            validate_url_no_ssrf("https://this-host-does-not-exist-abc123.example.invalid")

    def test_allowlisted_host_accepted(self) -> None:
        """Accept private IP when hostname is in allowlist."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
            patch(
                "syntara.core.lib.url_validation.get_settings",
                return_value=type("S", (), {"workflow_http_request_allowed_hosts": ["internal.example.com"]})(),
            ),
        ):
            validate_url_no_ssrf("https://internal.example.com")

    def test_non_allowlisted_host_rejected(self) -> None:
        """Reject private IP when hostname is not in allowlist."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
            patch(
                "syntara.core.lib.url_validation.get_settings",
                return_value=type("S", (), {"workflow_http_request_allowed_hosts": ["other.example.com"]})(),
            ),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("https://internal.example.com")

    def test_allowlist_multiple_hosts(self) -> None:
        """Accept when hostname matches one of multiple allowlisted hosts."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
            patch(
                "syntara.core.lib.url_validation.get_settings",
                return_value=type(
                    "S",
                    (),
                    {
                        "workflow_http_request_allowed_hosts": ["host-a.com", "host-b.com", "internal.example.com"],
                    },
                )(),
            ),
        ):
            validate_url_no_ssrf("https://internal.example.com")

    def test_ipv4_mapped_ipv6_rejected(self) -> None:
        """Reject IPv4-mapped IPv6 addresses (::ffff:x.x.x.x) targeting private IPs."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("::ffff:10.0.0.1")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("https://sneaky.example.com")

    def test_ipv4_mapped_ipv6_cloud_metadata_rejected(self) -> None:
        """Reject IPv4-mapped IPv6 targeting cloud metadata."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("::ffff:169.254.169.254")),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("https://sneaky.example.com")

    def test_allowlisted_host_resolving_to_metadata_rejected(self) -> None:
        """Reject allowlisted host if DNS rebinds to cloud metadata IP."""
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("169.254.169.254")),
            patch(
                "syntara.core.lib.url_validation.get_settings",
                return_value=type("S", (), {"workflow_http_request_allowed_hosts": ["evil.example.com"]})(),
            ),
            pytest.raises(ValueError, match="SSRF blocked"),
        ):
            validate_url_no_ssrf("https://evil.example.com")
