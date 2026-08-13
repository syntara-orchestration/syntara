"""Integration tests for integrations/lib/url_validation with allowlist behavior."""

from unittest.mock import patch

import pytest

from syntara.integrations.models.integration_configuration import AAPConfiguration


def _mock_getaddrinfo(ip: str) -> list[tuple[None, None, None, None, tuple[str, int]]]:
    """Return a mock getaddrinfo result for a given IP."""
    return [(None, None, None, None, (ip, 0))]


_PATCH_GETADDRINFO = "socket.getaddrinfo"
_PATCH_GET_SETTINGS = "syntara.integrations.lib.url_validation.get_settings"


def test_allowlisted_private_ip_accepted() -> None:
    """Private IP accepted when hostname is in integration_url_allowed_hosts."""
    with (
        patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
        patch(
            _PATCH_GET_SETTINGS,
            return_value=type("S", (), {"integration_url_allowed_hosts": ["aap.internal.corp"]})(),
        ),
    ):
        config = AAPConfiguration(
            base_url="http://aap.internal.corp",
            allow_http=True,
        )
    assert config.base_url == "http://aap.internal.corp"


def test_allowlist_does_not_permit_cloud_metadata() -> None:
    """Cloud metadata blocked even when hostname is allowlisted."""
    with (
        patch(
            _PATCH_GET_SETTINGS,
            return_value=type("S", (), {"integration_url_allowed_hosts": ["169.254.169.254"]})(),
        ),
        pytest.raises(ValueError, match="SSRF blocked"),
    ):
        AAPConfiguration(
            base_url="http://169.254.169.254",
            allow_http=True,
        )


def test_allow_http_false_blocks_http_for_public_url() -> None:
    """HTTP scheme rejected for public URL when allow_http=False."""
    with pytest.raises(ValueError, match="scheme must be https"):
        AAPConfiguration(
            base_url="http://aap.example.com",
            allow_http=False,  # default
        )


def test_allow_http_true_permits_http_for_public_url() -> None:
    """HTTP scheme accepted for public URL when allow_http=True."""
    with patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("93.184.216.34")):
        config = AAPConfiguration(
            base_url="http://aap.example.com",
            allow_http=True,
        )
    assert config.base_url == "http://aap.example.com"
