"""Shared validation for deployment and injected delivery-cache trust inputs."""

from uuid import UUID

from syntara.core.exceptions import SafeValueError


def validate_delivery_cache_trust_inputs(
    *,
    enabled: bool,
    cache_epoch: UUID | None,
    clock_error_bound_seconds: float | None,
    skew_seconds: float,
    ttl_seconds: int,
    retention_seconds: int,
) -> None:
    """Require an external epoch and attested clock error below the reserved margin.

    Field validators separately enforce positive, finite durations. The clock
    bound is a deployment attestation, not a runtime clock measurement; expiry
    reserves skew_seconds, which must strictly exceed that bound.
    """
    if cache_epoch is not None and cache_epoch.int == 0:
        msg = "Delivery cache epoch must be a nonzero deployment-managed UUID"
        raise SafeValueError(msg)
    if enabled and (
        cache_epoch is None
        or clock_error_bound_seconds is None
        or clock_error_bound_seconds >= skew_seconds
        or min(ttl_seconds, retention_seconds) <= skew_seconds
    ):
        msg = "Enabled delivery cache requires an external epoch, bounded clocks and a positive proof window"
        raise SafeValueError(msg)
