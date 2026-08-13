"""URL validation for integration base_url fields with SSRF protection."""

from urllib.parse import urlparse

from langchain_core._security._ssrf_protection import validate_safe_url

from syntara.core.config.base import get_settings
from syntara.core.lib.url_validation import _is_loopback


def validate_url_no_ssrf(url: str, *, allow_http: bool = False) -> None:
    """Validate an integration URL to mitigate SSRF attacks.

    Loopback addresses (127.0.0.0/8, ::1, localhost) are always permitted so that
    local integrations (e.g. a local MCP server on localhost) work without config.
    Other private/reserved IPs are rejected unless the hostname is listed in the
    integration_url_allowed_hosts setting. Cloud metadata endpoints are always
    blocked regardless of the allowlist.

    Args:
        url: The URL to validate.
        allow_http: If True, allow HTTP scheme (from integration security settings).

    Raises:
        ValueError: If the URL fails validation.

    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if _is_loopback(hostname):
        return

    allowed = {h.lower() for h in get_settings().integration_url_allowed_hosts}
    if hostname in allowed:
        validate_safe_url(url, allow_private=True, allow_http=allow_http)
    else:
        validate_safe_url(url, allow_private=False, allow_http=allow_http)
