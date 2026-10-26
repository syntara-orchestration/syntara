"""Immutable copies of committed delivery evidence; no payloads or mutable status."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from syntara.core.constants import EventDeliveryDefaults
from syntara.eventstreams.core.deduplication import DeliveryIdentity, DeliveryState, DeliveryValue, TerminalDelivery


def terminal_proof_key(identity: DeliveryIdentity, cache_epoch: UUID) -> str:
    """Keep external recovery epochs entirely outside durable identity encoding."""
    if cache_epoch.int == 0:
        msg = "A nonzero external cache epoch is required"
        raise ValueError(msg)
    return f"syntara:eventstreams:terminal:v1:{cache_epoch}:{identity.digest}"


class TerminalProof(DeliveryValue):
    """Versioned historical proof; future no-trigger outcomes still need discard gates."""

    schema_version: Literal[1]
    cache_epoch: UUID
    identity: DeliveryIdentity
    identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal[DeliveryState.SCHEDULED, DeliveryState.FILTERED, DeliveryState.REJECTED]
    resolved_at: AwareDatetime
    valid_until: AwareDatetime
    execution_id: UUID | None = None
    temporal_workflow_id: str | None = Field(default=None, min_length=1, max_length=255)
    temporal_run_id: str | None = Field(default=None, min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9._:-]+$")
    execution_confirmed_at: AwareDatetime | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version_type(cls, value: object) -> int:
        """JSON booleans and string coercion cannot stand in for a schema version."""
        if not isinstance(value, int) or isinstance(value, bool):
            msg = "Terminal proof schema version must be an integer"
            raise ValueError(msg)  # noqa: TRY004 - Pydantic validators require ValueError, not TypeError.
        return value

    @model_validator(mode="after")
    def validate_evidence(self) -> "TerminalProof":
        """Require internally consistent identity, expiry and scheduling confirmation."""
        if self.cache_epoch.int == 0 or self.identity_digest != self.identity.digest:
            msg = "Terminal proof identity or epoch is inconsistent"
            raise ValueError(msg)
        if self.valid_until <= self.resolved_at:
            msg = "Terminal proof expiry must follow original resolution"
            raise ValueError(msg)
        if self.outcome == DeliveryState.SCHEDULED:
            if (
                self.execution_id != self.identity.execution_id
                or self.temporal_workflow_id != self.identity.temporal_workflow_id
                or self.temporal_run_id is None
                or self.execution_confirmed_at is None
                or self.execution_confirmed_at > self.resolved_at
            ):
                msg = "Scheduled proof requires deterministic IDs and complete scheduling confirmation"
                raise ValueError(msg)
        elif any(
            value is not None
            for value in (
                self.execution_id,
                self.temporal_workflow_id,
                self.temporal_run_id,
                self.execution_confirmed_at,
            )
        ):
            msg = "No-trigger proof cannot carry scheduling evidence"
            raise ValueError(msg)
        if len(self.model_dump_json().encode("utf-8")) > EventDeliveryDefaults.TERMINAL_CACHE_MAX_ENTRY_BYTES:
            msg = "Terminal proof exceeds the serialized entry limit"
            raise ValueError(msg)
        return self

    def terminal(self) -> TerminalDelivery:
        """Convert only after the provider has checked authenticity and current policy."""
        return TerminalDelivery(
            identity=self.identity,
            state=self.outcome,
            resolved_at=self.resolved_at,
            execution_id=self.execution_id,
            temporal_run_id=self.temporal_run_id,
            execution_confirmed_at=self.execution_confirmed_at,
        )


class AuthenticatedTerminalProof(TerminalProof):
    """HMAC-SHA256 over every proof field, excluding this authentication tag.

    Schema v1 fixes the algorithm and signing purpose. Unsigned legacy entries
    are cache misses; the epoch and identity digest are not authentication keys.
    The inherited serialized limit includes this tag.
    """

    mac: str = Field(pattern=r"^[0-9a-f]{64}$")
