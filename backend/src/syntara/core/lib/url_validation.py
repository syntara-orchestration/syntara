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


def _is_resolution_failure(error: ValueError) -> bool:
    """Return True if a validate_safe_url ValueError is a DNS/network failure, not a policy block.

    langchain-core's ``validate_safe_url`` wraps the underlying cause: a resolved-but-blocked
    address surfaces with an ``SSRFBlockedError`` cause, while a DNS-resolution failure
    (``socket.gaierror``) or transient network error surfaces with an ``OSError`` cause
    (``gaierror`` is an ``OSError`` subclass; ``SSRFBlockedError`` is not). Only the latter is a
    connectivity problem rather than an SSRF policy violation, so it can be keyed on the cause
    type without brittle message matching.
    """
    return isinstance(error.__cause__, OSError)


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

    A host in *allowed_hosts* is operator-trusted, so a DNS-resolution or transient network
    failure for it is treated as a pass rather than a rejection: it is a connectivity problem,
    not an SSRF policy violation, and a host that cannot be resolved cannot be reached. This
    keeps the check from reporting a misleading "resolves to a private address" error for an
    unresolvable trusted host and from flaking when that host is momentarily unreachable; the
    resolved address is re-validated at request time. Non-allowlisted hosts still fail closed on
    resolution failure, and a trusted host that *does* resolve to a blocked address (e.g. cloud
    metadata) is still rejected.

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

    if hostname in allowed:
        try:
            validate_safe_url(url, allow_private=True, allow_http=allow_http)
        except ValueError as e:
            # Trusted host that could not be resolved/reached: defer to the request-time
            # re-check rather than rejecting a transient DNS/network failure as an SSRF block.
            if _is_resolution_failure(e):
                return
            raise
    else:
        validate_safe_url(url, allow_private=False, allow_http=allow_http)
