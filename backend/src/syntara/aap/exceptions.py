"""Domain exceptions for AAP proxy endpoints."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import NexusError


@fastapi_exception(handler="syntara.aap.error_handlers.aap_not_configured_handler")
class AAPNotConfiguredError(NexusError):
    """AAP Controller not configured (no env vars)."""


@fastapi_exception(handler="syntara.aap.error_handlers.aap_connection_error_handler")
class AAPConnectionError(NexusError):
    """Cannot connect to AAP Controller (network error, timeout)."""


@fastapi_exception(handler="syntara.aap.error_handlers.aap_authentication_error_handler")
class AAPAuthenticationError(NexusError):
    """AAP returned 401/403 — invalid token or credentials."""


@fastapi_exception(handler="syntara.aap.error_handlers.aap_upstream_error_handler")
class AAPUpstreamError(NexusError):
    """AAP returned an unexpected error (4xx/5xx other than auth)."""
