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


def validate_integration_configuration_no_ssrf(configuration: object) -> None:
    """Apply the integration SSRF policy to a configuration's ``base_url``.

    Single choke point routed through by every boundary that turns a stored
    integration base_url into an outbound request — write time (create/patch) and
    each runtime resolve/connect path (AAP proxy, workflow AAP resolution, LLM
    invocation, MCP tool connect). It reads ``base_url`` and the per-type
    ``allow_http`` flag off the configuration and delegates to
    :func:`validate_integration_url_no_ssrf`, so the policy (allowlist +
    https-by-default) lives in one place and cannot drift per call site.

    Because the check resolves DNS on every call, running it again at request time
    is defense in depth against DNS re-pointing after write time and against rows
    created before write-time validation existed.

    Configurations without a ``base_url`` (e.g. an LLM provider using its default
    endpoint) are a no-op.

    Args:
        configuration: An integration configuration exposing ``base_url`` and,
            optionally, ``allow_http``.

    Raises:
        ValueError: If the base_url resolves to a private, reserved, or cloud
            metadata address (and is not allowlisted).

    """
    base_url = getattr(configuration, "base_url", None)
    if not base_url:
        return
    allow_http = bool(getattr(configuration, "allow_http", False))
    validate_integration_url_no_ssrf(base_url, allow_http=allow_http)
