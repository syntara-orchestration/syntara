"""Process-local resource bounds; PostgreSQL remains the ownership authority."""

import asyncio

from syntara.core.config.base import get_settings
from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams.services.worker_gate import EventWorkerGate


class EventWorkerResources:
    """Share limits across consumers and recovery without sharing sessions."""

    def __init__(self, gate: EventWorkerGate | None = None) -> None:
        """Use fixed M1 preparation/finalization limits and the existing work bound."""
        self.preparation = asyncio.Semaphore(EventWorkerDefaults.PREPARATION_CONCURRENCY)
        self.finalization = asyncio.Semaphore(EventWorkerDefaults.FINALIZATION_CONCURRENCY)
        self.processing = asyncio.Semaphore(get_settings().event_processing_concurrency)
        self.placement = asyncio.Semaphore(EventWorkerDefaults.PLACEMENT_CONCURRENCY)
        self._gate = gate
        self._gate_failure_pending = False
        self.accepting = True

    @property
    def gate(self) -> EventWorkerGate | None:
        """Expose the shared process gate while composition is still incomplete."""
        return self._gate

    @gate.setter
    def gate(self, gate: EventWorkerGate | None) -> None:
        """Preserve failures and closed admission when installing the process gate."""
        if self._gate is not None and gate is not self._gate:
            msg = "Event worker gate is already installed"
            raise ValueError(msg)
        self._gate = gate
        if gate is not None:
            if self._gate_failure_pending:
                gate.database_failed()
                self._gate_failure_pending = False
            if not self.accepting:
                gate.close_admission()

    def close_admission(self) -> None:
        """Reject new preparation; already prepared work may still settle."""
        self.accepting = False
        if self.gate is not None:
            self.gate.close_admission()

    @property
    def scheduling_open(self) -> bool:
        """Existing frozen work may settle during shutdown while storage remains trusted."""
        return self.gate is not None and self.gate.scheduling_open

    def database_failed(self) -> None:
        """Share required durable failures with all local consumers and recovery."""
        if self.gate is not None:
            self.gate.database_failed()
        else:
            self._gate_failure_pending = True
