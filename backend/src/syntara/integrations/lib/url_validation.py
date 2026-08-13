"""URL validation for integration base_url fields with SSRF protection."""

from urllib.parse import urlparse

from langchain_core._security._ssrf_protection import validate_safe_url

from syntara.core.config.base import get_settings


def validate_url_no_ssrf(url: str, *, allow_http: bool = False) -> None:
    """Validate an integration URL to mitigate SSRF attacks.

    Uses integration_url_allowed_hosts setting to permit specific internal hosts.
    Cloud metadata endpoints are always blocked regardless of allowlist.

    Args:
        url: The URL to validate.
        allow_http: If True, allow HTTP scheme (from integration security settings).

    Raises:
        ValueError: If the URL fails validation.

    """
    allowed = {h.lower() for h in get_settings().integration_url_allowed_hosts}
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if hostname in allowed:
        validate_safe_url(url, allow_private=True, allow_http=allow_http)
    else:
        validate_safe_url(url, allow_private=False, allow_http=allow_http)
