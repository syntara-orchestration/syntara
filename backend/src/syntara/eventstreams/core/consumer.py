"""Shared types for the event consumer transport adapter.

These types sit at the ``core`` boundary so downstream initialization,
processing and supervision can depend on them without importing aiokafka
or the adapter implementation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import ConfigDict
from sqlmodel import SQLModel


class PositionStatus(StrEnum):
    """Outcome of a position read on a Kafka partition."""

    VERIFIED = "verified"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"
    UNCERTAIN = "uncertain"


class CommittedPositionResult(SQLModel):
    """Typed result of a single-partition committed-offset query.

    ``VERIFIED`` carries the confirmed next-offset. ``ABSENT`` means no
    committed offset exists (new consumer group or partition). ``UNAVAILABLE``
    means the query timed out or failed; ``error`` carries a sanitized reason.
    """

    partition: int
    status: PositionStatus
    offset: int | None = None
    error: str | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", frozen=True
    )

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
