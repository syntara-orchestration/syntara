"""Shared fixtures for integration unit tests."""

import ipaddress
from collections.abc import Generator
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

from syntara.integrations.lib.url_validation import validate_integration_url_no_ssrf


def _is_ssrf_probe(url: str) -> bool:
    """Return True if *url* targets an address that only a deliberate SSRF test would use.

    Loopback is intentionally excluded: the suite uses ``localhost``/``127.0.0.1`` as
    ordinary placeholders for local services, so those must stay bypassable. A hostname
    (e.g. ``gateway.example.com``) is also bypassable — it is a placeholder, not a probe.
    """
    host = (urlparse(url).hostname or "").strip("[]")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.is_loopback:
        return False
    return ip.is_private or ip.is_link_local or ip.is_reserved


@pytest.fixture(autouse=True)
def _skip_ssrf_validation(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Bypass write-time SSRF base_url validation for tests using placeholder hostnames.

    Integration configs in tests use non-resolvable hosts (e.g. gateway.example.com), so the
    DNS-resolving SSRF check at the create/patch boundary would reject them. Tests that
    exercise the SSRF check itself opt out with ``@pytest.mark.ssrf_enforced``.

    Safety net: the bypass still runs the real check for private/link-local/reserved/metadata
    IP literals, so an SSRF regression test that forgets the marker cannot silently pass while
    never exercising the check (e.g. a create with ``http://169.254.169.254`` is still rejected).
    """
    if request.node.get_closest_marker("ssrf_enforced"):
        yield
        return

    def _bypass(url: str, *, allow_http: bool = False) -> None:
        if _is_ssrf_probe(url):
            validate_integration_url_no_ssrf(url, allow_http=allow_http)

    with patch(
        "syntara.integrations.services.integration_service.validate_integration_url_no_ssrf",
        side_effect=_bypass,
    ):
        yield
