"""Canonical delivery identities and transactional repository value contracts."""

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Literal, Protocol
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

    @property
    def cache_key(self) -> str:
        """Return the optional terminal-reference cache key."""
        return f"syntara:eventstreams:dedup:v1:{self.digest}"


def input_fingerprint(input_data: object, context: object) -> str:
    """Hash frozen Execution input/context without duplicating either in the ledger."""
    encoded = json.dumps(
        {"input": input_data, "context": context},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


class DeliveryState(StrEnum):
    """Persisted admission states, independent of workflow completion."""

    IN_PROGRESS = "in_progress"
    SCHEDULED = "scheduled"
    FILTERED = "filtered"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class DeliveryExpectation(DeliveryValue):
    """Publication state that must still hold when admitting a new record."""

    published_version_id: UUID
    configuration_revision: int = Field(gt=0, strict=True)


class FrozenDeliveryBinding(DeliveryValue):
    """References frozen together with the ordinary pending Execution."""

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


class DeliveryClaim(DeliveryValue):
    """Database mutation capability; a Kafka ownership token is a separate concern."""

    identity: DeliveryIdentity
    token: UUID
    owner_worker_id: str = Field(min_length=1, max_length=255)
    lease_until: AwareDatetime
    binding: FrozenDeliveryBinding | None = None
    attempt_count: int = Field(default=0, ge=0)
    first_start_attempt_at: AwareDatetime | None = None
    temporal_run_id: str | None = Field(default=None, min_length=1, max_length=255)
    start_retry_deadline: AwareDatetime | None = None
    scheduling_failure_count: int = Field(default=0, ge=0)
    next_attempt_at: AwareDatetime | None = None
    last_error_code: str | None = Field(default=None, max_length=100)


class ClaimBusy(DeliveryValue):
    """Another current owner must finish or lose its lease."""

    lease_until: AwareDatetime


class ClaimLost(DeliveryValue):
    """The token or its lease no longer permits mutation."""

    reason: Literal["claim_lost"] = "claim_lost"


class RevisionChanged(DeliveryValue):
    """The requested publication/source is no longer available for new admission."""

    reason: Literal["revision_changed"] = "revision_changed"


class StorageBackpressure(DeliveryValue):
    """No new row may be admitted while capacity is unavailable or exhausted."""

    reason: Literal["storage_pressure"] = "storage_pressure"


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
        if self.state == DeliveryState.IN_PROGRESS:
            msg = "An in-progress delivery is not terminal evidence"
            raise ValueError(msg)
        if self.state == DeliveryState.SCHEDULED and (
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


class RecoveryReservation(DeliveryValue):
    """Source-wide evidence hold; never expires merely because its owner stops."""

    source_id: UUID
    token: UUID


class CleanupCandidate(DeliveryValue):
    """Evidence snapshot that must be rechecked after out-of-transaction verification."""

    identity: DeliveryIdentity
    resolved_at: AwareDatetime
    evidence_revision: int = Field(ge=0)


class CommittedPositionUnavailableError(Exception):
    """The adapter cannot establish authoritative committed progress."""


class CommittedPositionVerifier(Protocol):
    """Owned here; adapters verify current committed progress beyond this exact record."""

    async def is_committed_beyond(self, identity: DeliveryIdentity) -> bool:
        """Return verified progress; raise CommittedPositionUnavailableError on uncertainty."""
        ...


class DeliveryCapacityCheck(Protocol):
    """Separate admission gate; uncertainty must return false or raise."""

    async def permits_new_delivery(self) -> bool:
        """Check total retained delivery count with the approved hysteresis."""
        ...


class RecoveryEvidenceReservations(Protocol):
    """Recovery must commit a reservation before depending on retained evidence."""

    async def reserve_recovery(self, source_id: UUID, *, token: UUID | None = None) -> RecoveryReservation | None:
        """Reserve source evidence, failing closed when its lifecycle is unavailable."""
        ...

    async def release_recovery(self, reservation: RecoveryReservation) -> bool:
        """Release only after boundary changes and dependent recovery have settled."""
        ...


class TerminalReferenceCache(Protocol):
    """Disposable references; hits never replace a PostgreSQL lookup."""

    async def get(self, identity: DeliveryIdentity) -> str | None:
        """Read an optional terminal identity reference."""
        ...

    async def put(self, identity: DeliveryIdentity) -> None:
        """Cache a terminal identity only after its transaction commits."""
        ...


class DeliveryRepository[ExecutionPreparation: SQLModel](Protocol):
    """Session-bound operations; callers commit before treating results as durable."""

    async def acquire(
        self, identity: DeliveryIdentity, expected: DeliveryExpectation, owner_worker_id: str
    ) -> DeliveryClaim | ClaimBusy | TerminalDelivery | RevisionChanged | StorageBackpressure:
        """Insert or recover a claim without changing an existing terminal outcome."""
        ...

    async def renew(self, claim: DeliveryClaim) -> DeliveryClaim | ClaimLost:
        """Renew only a current, unexpired token using database time."""
        ...

    async def freeze(
        self, claim: DeliveryClaim, binding: FrozenDeliveryBinding, execution: ExecutionPreparation
    ) -> DeliveryClaim | ClaimLost | RevisionChanged:
        """Persist pending Execution preparation and freeze its immutable references."""
        ...

    async def record_start_attempt(
        self, claim: DeliveryClaim, *, retry_deadline: datetime | None = None, attempt_id: UUID | None = None
    ) -> DeliveryClaim | ClaimLost:
        """Persist the attempt before a caller may issue a Temporal start."""
        ...

    async def record_scheduling_failure(
        self, claim: DeliveryClaim, *, next_attempt_at: datetime, error_code: str
    ) -> DeliveryClaim | ClaimLost:
        """Persist retry budget and Execution metadata, releasing current ownership."""
        ...

    async def finalize_scheduled(
        self, claim: DeliveryClaim, acceptance: TemporalAcceptance
    ) -> TerminalDelivery | ClaimLost:
        """Confirm the delivery and ordinary Execution in the same transaction."""
        ...

    async def record_acceptance(
        self, claim: DeliveryClaim, acceptance: TemporalAcceptance
    ) -> DeliveryClaim | ClaimLost:
        """Retain verified acceptance without yet resolving scheduling."""
        ...

    async def finalize_without_execution(
        self, claim: DeliveryClaim, state: DeliveryState
    ) -> TerminalDelivery | ClaimLost:
        """Persist a no-trigger outcome without replacing prepared work."""
        ...

    async def defer(self, claim: DeliveryClaim, *, next_attempt_at: datetime, error_code: str) -> ClaimLost | None:
        """Release ownership for retry while preserving immutable evidence."""
        ...

    async def lookup_terminal(self, identity: DeliveryIdentity) -> TerminalDelivery | None:
        """Read authoritative retained evidence, including after Execution deletion."""
        ...

    async def claim_due(self, owner_worker_id: str, *, limit: int, prepared_only: bool = False) -> list[DeliveryClaim]:
        """Select bounded due unowned/expired work, including retired sources."""
        ...

    async def request_scheduling_retry(self, identity: DeliveryIdentity) -> bool:
        """Make unowned prepared work due without resetting any evidence or budget."""
        ...
