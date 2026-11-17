"""Bounded event-loop-local Kafka producers and ownership of late deliveries."""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from syntara.workflows.workflow_engine.activities.kafka_publish_errors import (
    KafkaPublishProducerUnavailableError,
    classify_publish_error,
)
from syntara.workflows.workflow_engine.models.kafka_publish import (
    KAFKA_PUBLISH_IDLE_SECONDS,
    KAFKA_PUBLISH_MAX_RECORD_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from aiokafka import AIOKafkaProducer
    from aiokafka.structs import RecordMetadata


@dataclass(eq=False, repr=False)
class ProducerEntry:
    """One counted producer, including startup and incomplete background shutdown."""

    key: str
    identity: str
    producer: AIOKafkaProducer
    ready: asyncio.Task[None] | None = None
    users: int = 0
    pending: int = 0
    last_used: float = field(default_factory=time.monotonic)
    retiring: bool = False
    cleanup: asyncio.Task[None] | None = None


@dataclass(repr=False)
class PublishSend:
    """A send remains owned even after its activity stops waiting."""

    task: asyncio.Task[RecordMetadata] | None = None
    enqueued: bool = False
    started: bool = False
    cancelled: bool = False

    def cancel_before_enqueue(self) -> None:
        """Stop pre-enqueue work when cancellation is observed by the activity.

        aiokafka's send coroutine can be cancelled before it returns a delivery
        future. Once it returns, the queued delivery keeps its counted owner.
        """
        self.cancelled = True
        if self.started and not self.enqueued and self.task is not None:
            self.task.cancel()

    def begin(self) -> None:
        """Observe cancellation even when it arrived before this task started."""
        self.started = True
        if self.cancelled:
            raise asyncio.CancelledError

    @property
    def may_have_delivered(self) -> bool:
        """Only a completed pre-enqueue failure establishes non-delivery."""
        return self.enqueued or self.task is None or not self.task.done()


class KafkaPublishPool:
    """Reuse producers without unbounded replacement or lost pending futures.

    All methods run on the owning event loop. Active, starting and retiring
    producers share one limit. Sends retain their count/bytes until actual
    settlement, independently of activity cancellation and timeout.
    """

    def __init__(self, concurrency: int, *, idle_seconds: float = KAFKA_PUBLISH_IDLE_SECONDS) -> None:
        """Size resource limits using the worker's activity concurrency."""
        if concurrency < 1 or not 0 < idle_seconds < float("inf"):
            msg = "Publish concurrency and idle expiry must be positive and finite"
            raise ValueError(msg)
        self.limit = concurrency
        self.byte_limit = concurrency * KAFKA_PUBLISH_MAX_RECORD_BYTES
        self.idle_seconds = idle_seconds
        self._entries: set[ProducerEntry] = set()
        self._condition = asyncio.Condition()
        self._pending = 0
        self._bytes = 0
        self._closing = False
        self._janitor: asyncio.Task[None] | None = None

    @contextlib.asynccontextmanager
    async def acquire(
        self,
        key: str,
        identity: str,
        factory: Callable[[], AIOKafkaProducer],
        *,
        on_admission: Callable[[ProducerEntry], None] | None = None,
    ) -> AsyncIterator[ProducerEntry]:
        """Wait for a compatible producer; the caller supplies the deadline."""
        async with self._condition:
            while True:
                if self._closing:
                    raise KafkaPublishProducerUnavailableError
                self._expire_idle()
                entry = next((item for item in self._entries if item.key == key and not item.retiring), None)
                if entry is not None:
                    break
                # An unused older snapshot need not occupy a slot for its full TTL.
                for item in tuple(self._entries):
                    if item.identity == identity and item.users == 0 and item.pending == 0:
                        self._retire(item)
                if len(self._entries) < self.limit:
                    entry = ProducerEntry(key, identity, factory())
                    self._entries.add(entry)
                    entry.ready = asyncio.create_task(self._start(entry))
                    entry.ready.add_done_callback(_consume_exception)
                    if self._janitor is None:
                        self._janitor = asyncio.create_task(self._expire_loop())
                    break
                await self._condition.wait()
            entry.users += 1
        try:
            if on_admission is not None:
                on_admission(entry)
            if entry.ready is not None:
                await asyncio.shield(entry.ready)
            yield entry
        finally:
            async with self._condition:
                entry.users -= 1
                entry.last_used = time.monotonic()
                self._condition.notify_all()

    async def _start(self, entry: ProducerEntry) -> None:
        try:
            await entry.producer.start()
        except BaseException:
            self._retire(entry)
            raise

    async def submit(
        self,
        entry: ProducerEntry,
        topic: str,
        value: bytes,
        key: bytes | None,
        headers: list[tuple[str, bytes | None]],
        size: int,
        before_send: Callable[[], Awaitable[None]] | None = None,
    ) -> PublishSend:
        """Reserve capacity before a send starts, retaining it until settlement."""
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._closing or (self._pending < self.limit and self._bytes + size <= self.byte_limit)
            )
            self._require_admission(entry)
            self._pending += 1
            self._bytes += size
            entry.pending += 1
        try:
            if before_send is not None:
                # Resource availability may have changed while awaiting a slot.
                await before_send()
            self._require_admission(entry)
        except BaseException:
            await self._release_send(entry, size)
            raise
        send = PublishSend()
        send.task = asyncio.create_task(self._deliver(entry, send, topic, value, key, headers, size))
        # Retrieve failures even if the activity timed out and no longer awaits it.
        send.task.add_done_callback(_consume_exception)
        return send

    def _require_admission(self, entry: ProducerEntry) -> None:
        if self._closing or entry.retiring:
            raise KafkaPublishProducerUnavailableError

    async def _deliver(
        self,
        entry: ProducerEntry,
        send: PublishSend,
        topic: str,
        value: bytes,
        key: bytes | None,
        headers: list[tuple[str, bytes | None]],
        size: int,
    ) -> RecordMetadata:
        try:
            send.begin()
            future = await entry.producer.send(topic, value=value, key=key, headers=headers)
            send.enqueued = True
            return await asyncio.shield(future)
        except Exception as exc:
            if classify_publish_error(exc)[2]:
                self._retire(entry)
            raise
        finally:
            await self._release_send(entry, size)

    async def _release_send(self, entry: ProducerEntry, size: int) -> None:
        async with self._condition:
            self._pending -= 1
            self._bytes -= size
            entry.pending -= 1
            entry.last_used = time.monotonic()
            self._condition.notify_all()

    def retire(self, entry: ProducerEntry) -> None:
        """Remove a fatally failed producer from admission, keeping it counted."""
        self._retire(entry)

    def _retire(self, entry: ProducerEntry) -> None:
        if entry.retiring:
            return
        entry.retiring = True
        entry.cleanup = asyncio.create_task(self._stop(entry))
        entry.cleanup.add_done_callback(_consume_exception)

    async def _stop(self, entry: ProducerEntry) -> None:
        # Never cancel public stop(): aiokafka can mark itself closed before
        # actually cleaning up its sender. Waiters shield this managed task.
        if entry.ready is not None and entry.ready is not asyncio.current_task():
            with contextlib.suppress(Exception):
                await asyncio.shield(entry.ready)
        await entry.producer.stop()
        async with self._condition:
            # Pending sends own their permits separately until they settle.
            await self._condition.wait_for(lambda: entry.pending == 0)
            self._entries.discard(entry)
            self._condition.notify_all()

    def _expire_idle(self) -> None:
        now = time.monotonic()
        for entry in tuple(self._entries):
            if entry.users == 0 and entry.pending == 0 and now - entry.last_used >= self.idle_seconds:
                self._retire(entry)

    def resume(self, concurrency: int) -> None:
        """Keep draining predecessors counted across an in-process worker restart."""
        if concurrency < 1:
            msg = "Publish concurrency must be positive"
            raise ValueError(msg)
        self.limit = concurrency
        self.byte_limit = concurrency * KAFKA_PUBLISH_MAX_RECORD_BYTES
        self._closing = False

    @property
    def has_retained_resources(self) -> bool:
        """Return whether replacement would lose live resource accounting."""
        return bool(self._entries) or self._pending > 0

    async def _expire_loop(self) -> None:
        while not self._closing:
            await asyncio.sleep(min(self.idle_seconds, 10))
            async with self._condition:
                self._expire_idle()

    async def close(self, wait_seconds: float = 5) -> None:
        """Stop admission and bound shutdown waiting without cancelling cleanup."""
        async with self._condition:
            self._closing = True
            for entry in tuple(self._entries):
                self._retire(entry)
            self._condition.notify_all()
        if self._janitor is not None:
            self._janitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._janitor
            self._janitor = None
        tasks = [entry.cleanup for entry in self._entries if entry.cleanup is not None]
        if tasks:
            # asyncio.wait does not cancel tasks when its timeout expires.
            await asyncio.wait(tasks, timeout=wait_seconds)


def _consume_exception(task: asyncio.Task[Any]) -> None:
    if not task.cancelled():
        task.exception()


_worker_pool: KafkaPublishPool | None = None


def initialize_kafka_publish_pool(concurrency: int) -> KafkaPublishPool:
    """Reuse retained accounting instead of allocating an uncounted replacement."""
    global _worker_pool  # noqa: PLW0603
    if _worker_pool is None or not _worker_pool.has_retained_resources:
        _worker_pool = KafkaPublishPool(concurrency)
    else:
        _worker_pool.resume(concurrency)
    return _worker_pool


def set_kafka_publish_pool(pool: KafkaPublishPool | None) -> None:
    """Bind the pool to the main workflow worker's lifecycle."""
    global _worker_pool  # noqa: PLW0603
    _worker_pool = pool


def get_kafka_publish_pool() -> KafkaPublishPool:
    """Require an explicitly initialized worker rather than an uncounted fallback."""
    if _worker_pool is None:
        msg = "Kafka publisher is not initialized"
        raise RuntimeError(msg)
    return _worker_pool
