"""Process-local resource bounds; PostgreSQL remains the ownership authority."""

import asyncio

from syntara.core.config.base import get_settings
from syntara.core.constants import EventWorkerDefaults


class EventWorkerResources:
    """Share limits across consumers and recovery without sharing sessions."""

    def __init__(self) -> None:
        """Use fixed M1 preparation/finalization limits and the existing work bound."""
        self.preparation = asyncio.Semaphore(EventWorkerDefaults.PREPARATION_CONCURRENCY)
        self.finalization = asyncio.Semaphore(EventWorkerDefaults.FINALIZATION_CONCURRENCY)
        self.processing = asyncio.Semaphore(get_settings().event_processing_concurrency)
        self.accepting = True

    def close_admission(self) -> None:
        """Reject new preparation; already prepared work may still settle."""
        self.accepting = False
