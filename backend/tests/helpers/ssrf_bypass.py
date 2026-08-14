"""Shared SSRF-bypass helper for tests that build integration configurations.

Integration configs in tests use non-resolvable placeholder hosts (e.g.
``gateway.example.com``), so the DNS-resolving SSRF check would reject them. This module
centralises the probe/patch logic so the unit and integration conftests build their
autouse ``_skip_ssrf_validation`` fixture on top of a single source of truth — the
safety-net rules cannot drift between the two.
"""

from __future__ import annotations

import contextlib
import ipaddress
from typing import TYPE_CHECKING
from unittest.mock import patch
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Iterator

# The single choke point every integration SSRF boundary routes through — write time
# (create/patch) and the runtime resolve/connect paths (AAP proxy, workflow AAP resolution,
# LLM invocation, MCP tool connect). Patching it here covers them all.
_SSRF_CHOKE_POINT = "syntara.integrations.lib.url_validation.validate_integration_url_no_ssrf"


def is_ssrf_probe(url: str) -> bool:
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


@contextlib.contextmanager
def bypass_integration_ssrf_validation() -> Iterator[None]:
    """Patch the integration SSRF choke point to skip validation for placeholder hosts.

    Safety net: the bypass still runs the real check for private/link-local/reserved/metadata
    IP literals, so an SSRF regression test that forgets ``@pytest.mark.ssrf_enforced`` cannot
    silently pass while never exercising the check (e.g. a create with
    ``http://169.254.169.254`` is still rejected).
    """
    # Imported lazily so importing this module (e.g. from a conftest) does not pull in
    # application code before pytest-cov starts tracking. The captured reference stays bound
    # to the real function, so the safety-net call below is not itself patched.
    from syntara.integrations.lib.url_validation import validate_integration_url_no_ssrf

    def _bypass(url: str, *, allow_http: bool = False) -> None:
        if is_ssrf_probe(url):
            validate_integration_url_no_ssrf(url, allow_http=allow_http)

    with patch(_SSRF_CHOKE_POINT, side_effect=_bypass):
        yield
