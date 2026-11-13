"""Canonical record identities and verified workflow acceptance values."""

import hashlib
import json
from enum import StrEnum
from typing import ClassVar, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, ConfigDict, Field, model_validator
from sqlmodel import SQLModel

from syntara.eventstreams.adapters.record_identity import RecordIdentity


class DeliveryValue(SQLModel):
    """Immutable, bounded coordination values; no event bodies or secrets."""

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", frozen=True
    )


class DeliveryIdentity(DeliveryValue):
    """Version one identity; workflow names and publication revisions are excluded."""

    identity_version: Literal[1] = 1
    deployment_id: UUID
    integration_identity: UUID
    source_id: UUID
    source_generation: int = Field(gt=0, strict=True)
    workflow_id: UUID
    subscription_id: UUID
    record: RecordIdentity

    def canonical_bytes(self) -> bytes:
        """Encode sorted ASCII JSON with no whitespace and decimal-string offsets."""
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")

    @property
    def digest(self) -> str:
        """Return the single SHA-256 identity used by every delivery consumer."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def execution_id(self) -> UUID:
        """Derive a deterministic UUID from the canonical digest in a fixed namespace."""
        return uuid5(NAMESPACE_URL, f"syntara:event-delivery:v1:{self.digest}")

    @property
    def temporal_workflow_id(self) -> str:
        """Return an identity independent of the mutable workflow name."""
        return f"event-v1-{self.digest}"


def input_fingerprint(input_data: object, context: object) -> str:
    """Hash original Execution input and context for acceptance comparison."""
    encoded = json.dumps(
        {"input": input_data, "context": context},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


class DeliveryState(StrEnum):
    """Confirmed handoff outcome, independent of workflow completion."""

    SCHEDULED = "scheduled"


class FrozenDeliveryBinding(DeliveryValue):
    """Original event references carried by signed workflow arguments."""

    workflow_version_id: UUID
    configuration_revision: int = Field(gt=0, strict=True)
    envelope_version: Literal[1] = 1
    runtime_credential_id: UUID | None
    connection_revision: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._:-]+$")
    execution_principal_id: UUID
    enabled_by: UUID | None
    received_at: AwareDatetime
    prepared_at: AwareDatetime
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class RevisionChanged(DeliveryValue):
    """The requested publication/source is no longer available for new admission."""

    reason: Literal["revision_changed"] = "revision_changed"


class TerminalDelivery(DeliveryValue):
    """Authoritative terminal evidence, provisional until the surrounding commit."""

    identity: DeliveryIdentity
    state: DeliveryState
    resolved_at: AwareDatetime
    execution_id: UUID | None = None
    temporal_run_id: str | None = Field(default=None, min_length=1, max_length=255)
    execution_confirmed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> "TerminalDelivery":
        """Reject unresolved values and incomplete scheduling evidence."""
        if (
            self.execution_id != self.identity.execution_id
            or self.temporal_run_id is None
            or self.execution_confirmed_at is None
        ):
            msg = "Scheduled delivery requires deterministic Execution and confirmed acceptance"
            raise ValueError(msg)
        return self


class TemporalAcceptance(DeliveryValue):
    """Verified acceptance supplied by a launcher; this module performs no RPCs."""

    execution_id: UUID
    temporal_workflow_id: str = Field(min_length=1, max_length=255)
    temporal_run_id: str = Field(min_length=1, max_length=255)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
