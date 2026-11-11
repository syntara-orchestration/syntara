"""Transport-neutral scheduling outcomes; none grants broker ownership."""

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from syntara.core.exceptions import SyntaraError
from syntara.eventstreams.core.deduplication import (
    DeliveryIdentity,
    DeliveryValue,
    TemporalAcceptance,
    TerminalDelivery,
)
from syntara.eventstreams.core.preparation import AcceptedWorkflow, PreparedExecution


class SchedulingFailureCode(StrEnum):
    """Bounded recovery reasons without customer data or exception text."""

    TEMPORAL_UNAVAILABLE = "temporal_unavailable"
    TEMPORAL_NOT_FOUND = "temporal_not_found"
    EVIDENCE_MISMATCH = "evidence_mismatch"
    HISTORY_UNAVAILABLE = "history_unavailable"
    HISTORY_EXPIRED = "history_expired"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    ATTEMPT_UNCERTAIN = "attempt_uncertain"


class EventLaunchError(SyntaraError):
    """Safe adapter failure; only explicitly transient failures may be probed."""

    def __init__(self, code: SchedulingFailureCode, *, transient: bool = True) -> None:
        """Retain only a bounded reason and its dependency retry classification."""
        self.code = code
        self.transient = transient
        super().__init__(code.value)


class RetryDelivery(DeliveryValue):
    """Unresolved scheduling with a local retry time; Kafka retains the record."""

    error_code: SchedulingFailureCode
    next_attempt_at: datetime
    circuit_open: bool


class BlockedDelivery(DeliveryValue):
    """Unresolved work requiring correction or explicit evidence recovery."""

    error_code: SchedulingFailureCode


class ResolvedDelivery(DeliveryValue):
    """Committed terminal evidence; partition ownership remains adapter-owned."""

    terminal: TerminalDelivery


class WorkflowLauncher(Protocol):
    """Finite Temporal operations over the frozen upstream preparation contract."""

    async def lookup(self, identity: DeliveryIdentity, *, run_id: str | None = None) -> AcceptedWorkflow:
        """Recover original signed arguments; only confirmed absence permits a new start."""
        ...

    async def start(self, prepared: PreparedExecution) -> TemporalAcceptance:
        """Start the stable identity or verify matching already-started evidence."""
        ...
