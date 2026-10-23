"""Shared types for the event consumer transport adapter.

These types sit at the ``core`` boundary so downstream initialization,
processing and supervision can depend on them without importing aiokafka
or the adapter implementation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Protocol, Self, runtime_checkable

from pydantic import ConfigDict, Field, model_validator
from sqlmodel import SQLModel

MAX_POSITION_OFFSET = (1 << 63) - 1


class PositionStatus(StrEnum):
    """Outcome of a position read on a Kafka partition."""

    VERIFIED = "verified"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"
    UNCERTAIN = "uncertain"


class CommittedPositionResult(SQLModel):
    """Typed result of a single-partition committed or boundary-offset query.

    ``VERIFIED`` carries the confirmed next-offset. ``ABSENT`` means no
    committed offset exists (new consumer group or partition). ``UNAVAILABLE``
    means the query timed out or failed; ``error`` carries a sanitized reason.
    Boundary queries never return ABSENT: missing, unknown or invalid offsets
    are UNCERTAIN. Only VERIFIED carries a non-negative signed-int64 offset.
    """

    partition: int
    status: PositionStatus
    offset: Annotated[int, Field(strict=True, ge=0, le=MAX_POSITION_OFFSET)] | None = None
    error: str | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", frozen=True
    )

    @model_validator(mode="after")
    def validate_verified_offset(self) -> Self:
        """Require an offset exactly when a result claims verified evidence."""
        if (self.status == PositionStatus.VERIFIED) != (self.offset is not None):
            msg = "Only verified position evidence must carry an offset"
            raise ValueError(msg)
        return self

    @staticmethod
    def verified(partition: int, offset: int) -> CommittedPositionResult:
        """Create a result with a confirmed committed offset."""
        return CommittedPositionResult(partition=partition, status=PositionStatus.VERIFIED, offset=offset)

    @staticmethod
    def absent(partition: int) -> CommittedPositionResult:
        """Create a result indicating no committed offset exists."""
        return CommittedPositionResult(partition=partition, status=PositionStatus.ABSENT)

    @staticmethod
    def unavailable(partition: int, error: str) -> CommittedPositionResult:
        """Create a result for a failed position query."""
        return CommittedPositionResult(partition=partition, status=PositionStatus.UNAVAILABLE, error=error)

    @staticmethod
    def uncertain(partition: int, reason: str) -> CommittedPositionResult:
        """Create a result where evidence is ambiguous."""
        return CommittedPositionResult(partition=partition, status=PositionStatus.UNCERTAIN, error=reason)


class IdentityStatus(StrEnum):
    """Evidence for one broker identifier; no status authorizes processing."""

    VERIFIED = "verified"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    UNCERTAIN = "uncertain"
    UNKNOWN_TOPIC = "unknown_topic"


class IdentityObservation(SQLModel):
    """One observed identifier, never an inferred identity match.

    Topic IDs use Kafka's URL-safe, unpadded base64 UUID representation.
    Unsupported means the negotiated protocol lacks the identifier; a null or
    zero identifier in a supporting protocol is uncertain evidence instead.
    """

    status: IdentityStatus
    value: str | None = None
    error: str | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        """Only verified observations may carry an identifier."""
        if self.status == IdentityStatus.VERIFIED:
            if self.value is None or not self.value.strip():
                msg = "Verified identity evidence requires a nonempty identifier"
                raise ValueError(msg)
        elif self.value is not None:
            msg = "Unverified identity evidence cannot carry an identifier"
            raise ValueError(msg)
        return self


class SourceIdentityObservation(SQLModel):
    """Cluster/topic evidence from one request under a checked assignment epoch.

    Callers compare identifiers and decide recovery policy. Before using this
    observation after another await, they must still check ownership/epoch via
    the adapter; successful reads never grant seek, processing or commit rights.
    """

    topic: str
    assignment_epoch: int
    cluster_id: IdentityObservation
    topic_id: IdentityObservation

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]


@runtime_checkable
class RebalanceCallback(Protocol):
    """Caller-implemented interface for partition assignment changes.

    The adapter invokes these during Kafka rebalance events. Implementations
    must not import the adapter or its client internals.
    """

    async def on_partitions_assigned(self, partitions: frozenset[int], epoch: int) -> None:
        """Handle newly assigned partitions at the given epoch."""
        ...

    async def on_partitions_revoked(self, partitions: frozenset[int], epoch: int) -> None:
        """Handle revoked partitions at the given epoch."""
        ...
