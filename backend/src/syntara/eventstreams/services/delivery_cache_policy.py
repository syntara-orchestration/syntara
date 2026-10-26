"""Shared terminal-proof expiry and durable-evidence retention policy."""

from datetime import datetime, timedelta
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from syntara.core.config.base import get_settings
from syntara.core.config.event_delivery import validate_delivery_cache_trust_inputs
from syntara.core.constants import EventDeliveryDefaults
from syntara.eventstreams.core.deduplication import DeliveryIdentity, DeliveryState, DeliveryValue
from syntara.eventstreams.core.terminal_proof import TerminalProof


class DeliveryEvidencePolicy(DeliveryValue):
    """Deployment-wide policy shared by cache users and cleanup.

    Before reducing TTL/retention or changing skew: close admission, drain old
    readers/writers, rotate the external epoch, then apply compatible settings
    everywhere before reopening. This provider cannot coordinate that rollout.
    A database restore/evidence correction also requires an external epoch rotation.
    """

    retention_seconds: int = Field(default=EventDeliveryDefaults.RETENTION_SECONDS, gt=0, strict=True)
    enabled: bool = False
    cache_epoch: UUID | None = None
    ttl_seconds: int = Field(default=EventDeliveryDefaults.TERMINAL_CACHE_TTL_SECONDS, gt=0, strict=True)
    timeout_seconds: float = Field(
        default=EventDeliveryDefaults.TERMINAL_CACHE_TIMEOUT_SECONDS, gt=0, allow_inf_nan=False
    )
    skew_seconds: float = Field(
        default=EventDeliveryDefaults.TERMINAL_CACHE_CLOCK_SKEW_SECONDS, gt=0, allow_inf_nan=False
    )
    clock_error_bound_seconds: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Deployment-attested pairwise clock error, not measured here; covered by skew_seconds",
    )

    @model_validator(mode="after")
    def validate_trust(self) -> Self:
        """Injected policies enforce the same safety inputs as deployment Settings."""
        validate_delivery_cache_trust_inputs(
            enabled=self.enabled,
            cache_epoch=self.cache_epoch,
            clock_error_bound_seconds=self.clock_error_bound_seconds,
            skew_seconds=self.skew_seconds,
            ttl_seconds=self.ttl_seconds,
            retention_seconds=self.retention_seconds,
        )
        return self

    @classmethod
    def from_settings(cls, *, retention_seconds: int | None = None) -> Self:
        """Load only environment/file settings, never a restored database value."""
        settings = get_settings()
        if (
            settings.event_delivery_cache_enabled
            and retention_seconds is not None
            and retention_seconds != settings.event_delivery_retention_seconds
        ):
            msg = "Enabled cache cleanup must use deployment retention or an explicit shared policy"
            raise ValueError(msg)
        return cls(
            retention_seconds=(
                settings.event_delivery_retention_seconds if retention_seconds is None else retention_seconds
            ),
            enabled=settings.event_delivery_cache_enabled,
            cache_epoch=settings.event_delivery_cache_epoch,
            ttl_seconds=settings.event_delivery_cache_ttl_seconds,
            timeout_seconds=settings.event_delivery_cache_timeout_seconds,
            skew_seconds=settings.event_delivery_cache_skew_seconds,
            clock_error_bound_seconds=settings.event_delivery_cache_clock_error_bound_seconds,
        )

    def proof_deadline(self, resolved_at: datetime) -> datetime:
        """Reserve the full skew margin, which already covers the attested bound.

        The bound is not measured or subtracted again here. Runtime clock-health
        failure disables the provider; reads and repopulation never extend expiry.
        """
        return resolved_at + timedelta(seconds=min(self.ttl_seconds, self.retention_seconds) - self.skew_seconds)

    def cleanup_after(self, resolved_at: datetime) -> datetime:
        """Evidence survives every trusted proof plus the cross-clock safety margin.

        proof_deadline + skew <= cleanup_after, independent of cache availability.
        Recovery holds and verified committed progress remain separate requirements.
        """
        return resolved_at + timedelta(seconds=self.retention_seconds)

    def trusts(self, proof: TerminalProof, identity: DeliveryIdentity, now: datetime) -> bool:
        """Clamp old proofs to shorter current settings; M1 trusts scheduling only."""
        return (
            self.enabled
            and now.tzinfo is not None
            and proof.cache_epoch == self.cache_epoch
            and proof.identity == identity
            and proof.identity_digest == identity.digest
            and proof.outcome == DeliveryState.SCHEDULED
            and proof.resolved_at <= now < min(proof.valid_until, self.proof_deadline(proof.resolved_at))
        )
