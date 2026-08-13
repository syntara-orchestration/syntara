"""URL validation for integration base_url fields with SSRF protection."""

from syntara.core.config.base import get_settings
from syntara.core.lib.url_validation import validate_url_no_ssrf


def validate_integration_url_no_ssrf(url: str, *, allow_http: bool = False) -> None:
    """Validate an integration base_url to mitigate SSRF attacks.

    Thin wrapper over the shared core SSRF policy (:func:`validate_url_no_ssrf`) bound to
    the ``integration_url_allowed_hosts`` allowlist — no policy logic is duplicated here,
    so the two domains cannot drift. Private, reserved, and loopback addresses
    (127.0.0.0/8, ::1, localhost) are rejected unless the hostname is allowlisted, so a
    local integration (e.g. an MCP server on localhost) is an explicit opt-in rather than
    an always-on bypass. Cloud metadata endpoints are always blocked.

    The distinct name (vs. the workflow-oriented core ``validate_url_no_ssrf``) keeps the
    policy difference — a different allowlist setting and https-by-default — explicit at
    call sites.

    Args:
        url: The URL to validate.
        allow_http: If True, allow HTTP scheme (from integration security settings).

    Raises:
        ValueError: If the URL fails validation.

    """
    validate_url_no_ssrf(
        url,
        allowed_hosts=get_settings().integration_url_allowed_hosts,
        allow_http=allow_http,
    )
