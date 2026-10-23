"""Ports owned by Kafka initialization/recovery, implemented by later callers."""

from collections.abc import Iterable
from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from pydantic import Field

from syntara.eventstreams.adapters.kafka_initial_position import PositionRequest, PositionValue
from syntara.eventstreams.core.consumer import CommittedPositionResult, SourceIdentityObservation


class AssignedPartitionClient(Protocol):
    """The completed transport interface; observations never grant ownership."""

    @property
    def topic(self) -> str:
        """Return the exact subscribed topic."""
        ...

    @property
    def group_id(self) -> str:
        """Return the immutable persisted consumer group."""
        ...

    @property
    def epoch(self) -> int:
        """Return the current assignment-local epoch."""
        ...

    @property
    def assignment(self) -> frozenset[int]:
        """Return currently owned partition numbers."""
        ...

    def position_operation(self, partition: int, *, expected_epoch: int) -> AbstractContextManager[bool]:
        """Exclude overlapping initialization/recovery on this shared client.

        Return False immediately when another operation owns the partition.
        Keep exclusion across assignment changes until the operation and its
        outstanding RPCs settle; an epoch change alone must not release it.
        """
        ...

    async def committed(
        self, partitions: Iterable[int], *, timeout_ms: int = 5000, expected_epoch: int | None = None
    ) -> dict[int, CommittedPositionResult]:
        """Read group commits with explicit missing/unavailable/uncertain results."""
        ...

    async def beginning_offsets(
        self, partitions: Iterable[int], *, expected_epoch: int, timeout_ms: int = 5000
    ) -> dict[int, CommittedPositionResult]:
        """Observe retained beginnings without resetting positions."""
        ...

    async def end_offsets(
        self, partitions: Iterable[int], *, timeout_ms: int = 5000, expected_epoch: int | None = None
    ) -> dict[int, CommittedPositionResult]:
        """Observe read-committed visible ends without resetting positions."""
        ...

    async def observe_source_identity(
        self, *, expected_epoch: int, timeout_ms: int = 5000
    ) -> SourceIdentityObservation:
        """Observe available cluster/topic identifiers without auto-creating topics."""
        ...

    async def seek(self, partition: int, offset: int, *, expected_epoch: int) -> None:
        """Seek only while this partition and epoch are still owned."""
        ...

    async def commit(self, offsets: dict[int, int], *, expected_epoch: int) -> None:
        """Commit only the explicit map under current assignment ownership."""
        ...


class DrainEvidence(PositionValue):
    """Explicit fail-closed evidence, not a cancellation or commit capability.

    Quiescence means conflicting processing tasks have drained and remain fenced
    by the supplied recovery token. It does not establish the outcome of an RPC
    already sent: the service must still repair every prepared delivery.
    Retained evidence is complete only when durable evidence covers the proposed
    retained reading window; elapsed time or an empty ledger is insufficient.
    Unknown permanent-content status must be treated as an active error gate.
    """

    quiescent: bool = Field(strict=True)
    retained_evidence_complete: bool = Field(strict=True)
    permanent_content_error: bool = Field(strict=True)


class PartitionRecoveryControl(Protocol):
    """Close/drain/fence contract; no future worker implementation is imported.

    Callers retain the fence through failed/interrupted recovery and only reopen
    after a READY result and a fresh lifecycle/assignment check. These methods
    must have bounded drain/check operations and never cancel an accepted workflow
    to make recovery appear complete. Database holds close cross-process new
    admission; this port also fences assignment-local tasks and queued commits.
    """

    async def close_and_drain(self, request: PositionRequest, *, token: UUID, boundary: int) -> DrainEvidence:
        """Drain conflicting work and report evidence for this exact recovery boundary."""
        ...

    async def is_fenced(self, request: PositionRequest, *, token: UUID) -> bool:
        """Verify the same recovery operation still fences local tasks and queued commits."""
        ...
