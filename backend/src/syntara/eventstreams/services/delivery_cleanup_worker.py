"""Independent, bounded delivery cleanup within each existing Kafka worker."""

import asyncio
import math
import random
from contextlib import suppress

import structlog
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.constants import EventDeliveryDefaults, FieldLimits
from syntara.eventstreams.adapters.kafka_retention_verifier import KafkaRetentionVerifier
from syntara.eventstreams.services.delivery_retention_service import EventDeliveryRetentionService
from syntara.eventstreams.services.worker_resources import EventWorkerResources

logger = structlog.stdlib.get_logger(__name__)


class EventDeliveryCleanupWorker:
    """Scan without a placement lease or active consumers; never coordinate via Redis.

    One batch runs at a time per process, with its own deadline and at most one
    source probe client. Existing lifecycle locks make overlapping replicas safe.
    Continue through full/protected pages; back off between completed sweeps.
    """

    def __init__(
        self,
        retention: EventDeliveryRetentionService,
        verifier: KafkaRetentionVerifier,
        resources: EventWorkerResources,
        *,
        batch_limit: int = EventDeliveryDefaults.CLEANUP_BATCH_LIMIT,
        idle_seconds: float = EventDeliveryDefaults.CLEANUP_IDLE_SECONDS,
        batch_seconds: float = EventDeliveryDefaults.CLEANUP_BATCH_TIMEOUT_SECONDS,
    ) -> None:
        """Inject cleanup services and bound each batch and idle interval."""
        if type(batch_limit) is not int or not 1 <= batch_limit <= FieldLimits.MAX_ITEMS_PER_PAGE:
            msg = "Cleanup batch limit must be between 1 and 100"
            raise ValueError(msg)
        if not all(math.isfinite(value) and value > 0 for value in (idle_seconds, batch_seconds)):
            msg = "Cleanup deadlines and intervals must be positive and finite"
            raise ValueError(msg)
        self._retention = retention
        self._verifier = verifier
        self._resources = resources
        self._batch_limit = batch_limit
        self._idle_seconds = idle_seconds
        self._batch_seconds = batch_seconds
        self._closing = False
        self._scanned = 0
        self._tick_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start once; readiness and subscription ownership are not prerequisites."""
        if self._task is not None and not self._task.done():
            return
        self._closing = False
        self._task = asyncio.create_task(self._run(), name="event-delivery-cleanup")

    def close_batches(self) -> None:
        """Fence new cleanup synchronously before process admission closes."""
        self._closing = True

    async def stop(self) -> None:
        """Cancel bounded work; verifier.batch disposes its client before exit."""
        self.close_batches()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def tick(self) -> int:
        """Run one fair page under shared database trust, retaining uncertain work."""
        async with self._tick_lock:
            self._scanned = 0
            if self._closing or not self._resources.accepting or not self._resources.scheduling_open:
                return 0
            removed = 0
            try:
                # Close the probe outside the batch deadline, under its own
                # short deadline, including when the scan is cancelled.
                async with self._verifier.batch():
                    async with asyncio.timeout(self._batch_seconds):
                        removed = await self._retention.cleanup(limit=self._batch_limit)
            except SQLAlchemyError:
                self._resources.database_failed()
                logger.warning("event_delivery_cleanup_database_unavailable")
            except TimeoutError:
                logger.warning("event_delivery_cleanup_batch_deadline")
            finally:
                self._scanned = self._retention.last_scan_count
            if self._scanned:
                logger.debug("event_delivery_cleanup_batch", scanned=self._scanned, removed=removed)
            return removed

    async def _run(self) -> None:
        while not self._closing:
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001 - maintenance failures must not stop ingestion
                self._scanned = 0
                logger.warning("event_delivery_cleanup_failed", error_type=type(exc).__name__)
            delay = (
                EventDeliveryDefaults.CLEANUP_BATCH_YIELD_SECONDS
                if self._scanned
                else self._idle_seconds * random.uniform(0.9, 1.1)  # noqa: S311 - scheduling jitter
            )
            await asyncio.sleep(delay)
