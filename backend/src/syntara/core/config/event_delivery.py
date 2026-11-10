"""Shared validation for deployment and injected delivery-cache trust inputs."""

from uuid import UUID

from pydantic import ValidationError, ValidatorFunctionWrapHandler

from syntara.core.exceptions import SafeValueError


def parse_delivery_cache_trust_input(value: object, handler: ValidatorFunctionWrapHandler) -> object:
    """Treat an unparseable epoch or clock bound as missing cache trust."""
    try:
        return handler(value)
    except ValidationError:
        return None


def validate_delivery_cache_trust_inputs(
    *,
    enabled: bool,
    cache_epoch: UUID | None,
    clock_error_bound_seconds: float | None,
    skew_seconds: float,
    ttl_seconds: int,
    retention_seconds: int,
) -> bool:
    """Validate the proof window and enable caching only with trusted inputs.

    Field validators separately enforce positive, finite durations. The clock
    bound is a deployment attestation, not a runtime clock measurement; expiry
    reserves skew_seconds, which must strictly exceed that bound.
    """
    if enabled and min(ttl_seconds, retention_seconds) <= skew_seconds:
        msg = "Enabled delivery cache requires a positive proof window"
        raise SafeValueError(msg)
    return (
        enabled
        and cache_epoch is not None
        and cache_epoch.int != 0
        and clock_error_bound_seconds is not None
        and clock_error_bound_seconds < skew_seconds
    )
