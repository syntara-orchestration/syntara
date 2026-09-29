"""Use the same DNS and cloud-metadata policy as the workflow HTTP activity."""

from urllib.parse import urlsplit

from langchain_core._security._ssrf_protection import validate_safe_url

from .runtime import get_settings


def validate_url_no_ssrf(url: str) -> None:
    """Apply the workflow HTTP allowlist and metadata protections."""
    hostname = (urlsplit(url).hostname or "").lower()
    allowed = {host.lower() for host in get_settings().workflow_http_request_allowed_hosts}
    validate_safe_url(url, allow_private=hostname in allowed, allow_http=True)
