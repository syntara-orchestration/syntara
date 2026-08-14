"""URL validation utilities for SSRF prevention.

Ensures host URLs contain only scheme, hostname, and optional port.
Delegates SSRF IP/hostname checks to langchain-core's validate_safe_url.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING
from urllib.parse import ParseResult, urlparse

from langchain_core._security._ssrf_protection import validate_safe_url

from syntara.core.config.base import get_settings

if TYPE_CHECKING:
    from collections.abc import Iterable

_ALLOWED_SCHEMES = frozenset({"https", "http"})
_HTTPS_ONLY = frozenset({"https"})
_LOOPBACK_V4_NETWORK = ipaddress.IPv4Network("127.0.0.0/8")
_LOOPBACK_V6 = ipaddress.IPv6Address("::1")
_DEFAULT_PORTS: dict[str, int] = {"https": 443, "http": 80}


def _check_disallowed_components(
    parsed: ParseResult,
    *,
    label: str = "Host URL",
    allow_path: bool = False,
) -> None:
    """Raise ValueError if the parsed URL contains disallowed components."""
    if "@" in parsed.netloc or "\\" in parsed.netloc:
        msg = f"{label} must not contain userinfo (@) or backslash characters."
        raise ValueError(msg)

    if not allow_path and parsed.path and parsed.path != "/":
        msg = (
            f"{label} must not contain a path. Use only scheme://hostname[:port], e.g., https://controller.example.com"
        )
        raise ValueError(msg)

    if parsed.query:
        msg = f"{label} must not contain a query string."
        raise ValueError(msg)

    if parsed.fragment:
        msg = f"{label} must not contain a fragment."
        raise ValueError(msg)


def _normalize_host(parsed: ParseResult) -> str:
    """Build normalized scheme://host[:port] from parsed URL, re-adding IPv6 brackets."""
    hostname = parsed.hostname or ""
    host = f"[{hostname}]" if ":" in hostname else hostname
    port = parsed.port
    if port and port != _DEFAULT_PORTS.get(parsed.scheme):
        return f"{parsed.scheme}://{host}:{port}"
    return f"{parsed.scheme}://{host}"


def _is_loopback(hostname: str) -> bool:
    """Return True if *hostname* is a loopback address (127.0.0.0/8, ::1, or ``localhost``)."""
    if hostname == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv4Address):
        return addr in _LOOPBACK_V4_NETWORK
    return addr == _LOOPBACK_V6


def _parse_and_validate(url: str, *, label: str, allow_http: bool) -> ParseResult:
    """Parse a URL and validate scheme and hostname."""
    url = url.strip() if url else ""
    if not url:
        msg = f"{label} must not be empty."
        raise ValueError(msg)

    parsed = urlparse(url)

    if not parsed.scheme:
        msg = f"{label} must include a scheme (e.g., https://). Got: '{url}'"
        raise ValueError(msg)

    effective_allow_http = allow_http
    if not effective_allow_http and parsed.hostname and _is_loopback(parsed.hostname):
        effective_allow_http = True

    allowed = _ALLOWED_SCHEMES if effective_allow_http else _HTTPS_ONLY
    if parsed.scheme not in allowed:
        schemes = ", ".join(sorted(allowed))
        msg = f"{label} scheme must be {schemes}. Got: '{parsed.scheme}'"
        raise ValueError(msg)

    if not parsed.hostname:
        msg = f"{label} must include a hostname."
        raise ValueError(msg)

    return parsed


def validate_host_url(url: str, *, allow_http: bool = False) -> str:
    """Validate and normalize a host URL to scheme://hostname[:port].

    Rejects URLs containing paths, query strings, or fragments to prevent
    SSRF via URL path injection.

    Args:
        url: The URL to validate.
        allow_http: If True, allow http:// scheme. Default requires https://.

    Returns:
        Normalized URL as ``scheme://hostname[:port]`` (port omitted if default).

    Raises:
        ValueError: If the URL contains disallowed components or an invalid scheme.

    """
    parsed = _parse_and_validate(url, label="Host URL", allow_http=allow_http)
    _check_disallowed_components(parsed, label="Host URL")
    return _normalize_host(parsed)


def validate_endpoint_url(url: str, *, allow_http: bool = False) -> str:
    """Validate an endpoint URL that may include a path.

    Like :func:`validate_host_url` but permits a URL path component, which
    is required for services mounted at a subpath (e.g. MCP servers at
    ``http://host:8765/mcp``).  Query strings, fragments, and userinfo are
    still rejected.

    Returns:
        The URL unchanged (not normalized to host-only).

    """
    parsed = _parse_and_validate(url, label="Endpoint URL", allow_http=allow_http)
    _check_disallowed_components(parsed, label="Endpoint URL", allow_path=True)
    return url


def validate_url_no_ssrf(
    url: str,
    *,
    allowed_hosts: Iterable[str] | None = None,
    allow_http: bool = True,
) -> None:
    """Validate a URL to mitigate SSRF attacks.

    Shared SSRF policy for all domains. Delegates to langchain-core's validate_safe_url
    which resolves the hostname and rejects private, loopback, link-local, reserved,
    cloud metadata, and Kubernetes internal DNS addresses. Hosts in *allowed_hosts*
    bypass the private/loopback check (allowing RFC1918 and loopback targets) but cloud
    metadata endpoints are always blocked regardless of the allowlist.

    The check fails closed on DNS-resolution or network failure for every host, allowlisted or
    not. Resolution must succeed so that the resolved address can be inspected; there is no
    later request-time re-validation (callers hand the URL straight to the HTTP client), so a
    soft-pass here would be the only gate. Deferring an unresolvable allowlisted host would be
    unsafe: DNS can return NXDOMAIN at check time yet resolve to a blocked address (e.g. cloud
    metadata) at connect time. A trusted host that resolves to a blocked address is always
    rejected, so cloud metadata endpoints stay blocked regardless of the allowlist.

    Args:
        url: The URL to validate.
        allowed_hosts: Hostnames permitted to resolve to private/loopback addresses.
            Defaults to the ``workflow_http_request_allowed_hosts`` setting so existing
            workflow HTTP callers keep their policy; other domains (e.g. integrations)
            pass their own allowlist explicitly via a domain-specific wrapper such as
            ``validate_integration_url_no_ssrf``.
        allow_http: If True, allow the http scheme in addition to https.

    Raises:
        ValueError: If the URL fails validation.

    """
    if allowed_hosts is None:
        allowed_hosts = get_settings().workflow_http_request_allowed_hosts
    allowed = {h.lower() for h in allowed_hosts}
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    # Mirror the scheme-layer loopback exception (see _parse_and_validate): loopback hosts
    # are always permitted over HTTP. Without this, the scheme layer accepts
    # http://localhost while this SSRF gate rejects it as "scheme 'http' not allowed",
    # so an allowlisted loopback host with allow_http=False would fail here. Reachability
    # is still gated by allow_private below, which requires the host to be allowlisted.
    effective_allow_http = allow_http or _is_loopback(hostname)

    if hostname in allowed:
        validate_safe_url(url, allow_private=True, allow_http=effective_allow_http)
    else:
        validate_safe_url(url, allow_private=False, allow_http=effective_allow_http)
