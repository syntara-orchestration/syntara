"""NATS JetStream wake-up transport.

The broker only delivers an advisory :class:`WakeHint`.  Task selection and
ownership remain in the execution store, which is why a redelivered hint is
safe to process more than once.

``nats-py`` is intentionally imported only when this adapter is connected.
That keeps the HTTP and Temporal PoCs usable in environments which have not
installed the optional JetStream dependency.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Protocol

from pydantic import ValidationError

from scheduler_wakeup_poc.contracts import PassResult, PublishReceipt, WakeHint

if TYPE_CHECKING:
    from types import ModuleType

WakeHandler = Callable[[WakeHint], Awaitable[PassResult]]
InvalidHintHandler = Callable[[bytes, str], Awaitable[None]]


class JetStreamUnavailableError(RuntimeError):
    """Raised only when the optional ``nats-py`` package is unavailable."""


class InvalidWakeHintError(ValueError):
    """A broker message did not contain a supported :class:`WakeHint`."""


class JetStreamMessage(Protocol):
    """Subset of an nats-py message used by the receiver."""

    data: bytes

    async def ack(self) -> None:
        """Acknowledge successful processing."""

    async def in_progress(self) -> None:
        """Extend the acknowledgement deadline."""

    async def term(self) -> None:
        """Terminate delivery of an invalid message."""


class PullSubscription(Protocol):
    """Subset of the nats-py pull-subscription API used by this PoC."""

    async def fetch(self, batch: int, timeout: float) -> list[JetStreamMessage]:  # noqa: ASYNC109
        """Fetch up to ``batch`` messages, waiting at most ``timeout`` seconds."""


class JetStreamPublishAck(Protocol):
    """The durable stream sequence returned by a successful publish."""

    seq: int


class JetStreamPublisherClient(Protocol):
    """Subset of the JetStream client API used by the publisher."""

    async def publish(
        self,
        subject: str,
        payload: bytes,
        *,
        headers: dict[str, str],
    ) -> JetStreamPublishAck:
        """Publish one payload and wait for the stream acknowledgement."""


class JetStreamConsumerClient(JetStreamPublisherClient, Protocol):
    """Subset of the JetStream API used to bind a shared pull consumer."""

    async def pull_subscribe(self, subject: str, *, durable: str) -> PullSubscription:
        """Bind the named durable pull consumer."""


class JetStreamAdminClient(Protocol):
    """Subset of the JetStream management API used during PoC startup."""

    async def stream_info(self, stream: str) -> object:
        """Return stream metadata or raise the broker's not-found error."""

    async def add_stream(self, config: object) -> object:
        """Create a stream from its native client configuration."""

    async def consumer_info(self, stream: str, consumer: str) -> object:
        """Return consumer metadata or raise the broker's not-found error."""

    async def add_consumer(self, stream: str, config: object) -> object:
        """Create a durable consumer from its native client configuration."""


@dataclass(frozen=True, slots=True)
class JetStreamSettings:
    """Run-scoped JetStream resource names and consumer timing."""

    stream: str
    subject: str
    durable_consumer: str = "scheduler-wakeups"
    servers: tuple[str, ...] = ("nats://127.0.0.1:4222",)
    ack_wait_seconds: float = 5.0
    progress_interval_seconds: float = 2.0
    fetch_timeout_seconds: float = 1.0
    max_bytes: int = 256 * 1024 * 1024
    duplicate_window_seconds: float = 600.0

    @classmethod
    def for_run(
        cls,
        run_id: str,
        *,
        servers: Iterable[str] = ("nats://127.0.0.1:4222",),
        subject_prefix: str = "execution.scheduler.wake",
    ) -> JetStreamSettings:
        """Create the stream subject described by the PoC handoff document."""
        compact_run_id = run_id.replace("-", "")
        return cls(
            stream=f"POC_WAKE_{compact_run_id}",
            subject=f"{subject_prefix}.poc.{run_id}.*",
            servers=tuple(servers),
        )

    def subject_for_queue(self, queue: str) -> str:
        """Return the exact subject used to publish an advisory queue hint."""
        if not queue or "." in queue or "*" in queue or ">" in queue:
            msg = f"queue {queue!r} cannot be represented as one JetStream subject token"
            raise ValueError(msg)
        return f"{self.subject.removesuffix('.*')}.{queue}"


def _load_nats() -> ModuleType:
    """Import nats-py at the optional adapter boundary."""
    try:
        return importlib.import_module("nats")
    except ModuleNotFoundError as exc:
        msg = "JetStream PoC requires optional dependency nats-py; install the scheduler-wakeup JetStream extra"
        raise JetStreamUnavailableError(msg) from exc


class JetStreamWakePublisher:
    """Publishes durable wake hints with event-id broker de-duplication."""

    def __init__(self, jetstream: JetStreamPublisherClient, settings: JetStreamSettings) -> None:
        """Build a publisher around an already connected JetStream client."""
        self._jetstream = jetstream
        self._settings = settings

    @classmethod
    async def connect(cls, settings: JetStreamSettings) -> JetStreamWakePublisher:
        """Connect a standalone publisher, without importing nats-py at module load."""
        nats = _load_nats()
        connection = await nats.connect(servers=list(settings.servers))
        publisher = cls(connection.jetstream(), settings)
        publisher._connection = connection
        return publisher

    async def close(self) -> None:
        """Close a connection created by :meth:`connect`, if this instance owns one."""
        connection = getattr(self, "_connection", None)
        if connection is not None:
            await connection.close()

    async def publish(self, hint: WakeHint) -> PublishReceipt:
        """Await JetStream acceptance before returning a durable receipt."""
        ack = await self._jetstream.publish(
            self._settings.subject_for_queue(hint.queue),
            hint.model_dump_json().encode(),
            headers={"Nats-Msg-Id": str(hint.event_id)},
        )
        sequence = getattr(ack, "seq", None)
        transport_ref = str(sequence) if sequence is not None else None
        return PublishReceipt(acceptance="durable", transport_ref=transport_ref)


class JetStreamWakeReceiver:
    """Shared durable pull-consumer which acknowledges only after a full drain."""

    def __init__(
        self,
        subscription: PullSubscription,
        handler: WakeHandler,
        settings: JetStreamSettings,
        *,
        accepted_queues: set[str] | None = None,
        on_invalid_hint: InvalidHintHandler | None = None,
    ) -> None:
        """Bind the shared durable consumer to a scheduler pass handler."""
        self._subscription = subscription
        self._handler = handler
        self._settings = settings
        self._accepted_queues = accepted_queues
        self._on_invalid_hint = on_invalid_hint

    @classmethod
    async def connect(
        cls,
        settings: JetStreamSettings,
        handler: WakeHandler,
        *,
        accepted_queues: set[str] | None = None,
        on_invalid_hint: InvalidHintHandler | None = None,
    ) -> JetStreamWakeReceiver:
        """Connect one scheduler replica to the shared durable consumer."""
        nats = _load_nats()
        connection = await nats.connect(servers=list(settings.servers))
        jetstream = connection.jetstream()
        subscription = await jetstream.pull_subscribe(settings.subject, durable=settings.durable_consumer)
        receiver = cls(
            subscription,
            handler,
            settings,
            accepted_queues=accepted_queues,
            on_invalid_hint=on_invalid_hint,
        )
        receiver._connection = connection
        return receiver

    async def close(self) -> None:
        """Close a connection created by :meth:`connect`, if this instance owns one."""
        connection = getattr(self, "_connection", None)
        if connection is not None:
            await connection.close()

    async def receive_once(self) -> bool:
        """Fetch and handle one message; return ``False`` for an idle fetch timeout.

        Transient scheduling failures deliberately escape without an ack so
        JetStream can redeliver the message after ``AckWait``.
        """
        try:
            messages = await self._subscription.fetch(1, timeout=self._settings.fetch_timeout_seconds)
        except TimeoutError:
            return False
        if not messages:
            return False
        await self._handle_message(messages[0])
        return True

    async def serve(self, stop_event: asyncio.Event) -> None:
        """Keep one blocking pull fetch active until the scheduler stops."""
        while not stop_event.is_set():
            await self.receive_once()

    async def _handle_message(self, message: JetStreamMessage) -> None:
        try:
            hint = WakeHint.model_validate_json(message.data)
            self._validate_queue(hint.queue)
        except (InvalidWakeHintError, ValidationError) as exc:
            await self._terminate_invalid(message, exc)
            return

        progress_task = asyncio.create_task(self._send_progress(message))
        try:
            while True:
                result = await self._handler(hint)
                if not result.immediate_more:
                    break
            await message.ack()
        finally:
            progress_task.cancel()
            with suppress(asyncio.CancelledError):
                await progress_task

    def _validate_queue(self, queue: str) -> None:
        if self._accepted_queues is not None and queue not in self._accepted_queues:
            error_message = f"queue {queue!r} is not registered on this scheduler"
            raise InvalidWakeHintError(error_message)

    async def _terminate_invalid(self, message: JetStreamMessage, exc: Exception) -> None:
        if self._on_invalid_hint is not None:
            await self._on_invalid_hint(bytes(message.data), str(exc))
        await message.term()

    async def _send_progress(self, message: JetStreamMessage) -> None:
        while True:
            await asyncio.sleep(self._settings.progress_interval_seconds)
            await message.in_progress()


async def ensure_jetstream_resources(jetstream: JetStreamAdminClient, settings: JetStreamSettings) -> None:
    """Create the run stream and its single shared durable consumer if absent.

    This function is intentionally separate from publisher/receiver connection
    so deployment startup can register resources before either role is ready.
    """
    try:
        api = importlib.import_module("nats.js.api")
        errors = importlib.import_module("nats.js.errors")
    except ModuleNotFoundError as exc:
        msg = "JetStream PoC requires optional dependency nats-py; install the scheduler-wakeup JetStream extra"
        raise JetStreamUnavailableError(msg) from exc

    not_found_error = errors.NotFoundError
    api_error = errors.APIError
    stream_config = api.StreamConfig(
        name=settings.stream,
        subjects=[settings.subject],
        retention=api.RetentionPolicy.WORK_QUEUE,
        storage=api.StorageType.FILE,
        discard=api.DiscardPolicy.NEW,
        max_bytes=settings.max_bytes,
        duplicate_window=settings.duplicate_window_seconds,
    )
    try:
        await jetstream.stream_info(settings.stream)
    except not_found_error:
        try:
            await jetstream.add_stream(stream_config)
        except api_error:
            # Another initializer may have created this resource after our read.
            await jetstream.stream_info(settings.stream)

    consumer_config = api.ConsumerConfig(
        durable_name=settings.durable_consumer,
        filter_subject=settings.subject,
        deliver_policy=api.DeliverPolicy.ALL,
        ack_policy=api.AckPolicy.EXPLICIT,
        ack_wait=settings.ack_wait_seconds,
    )
    try:
        await jetstream.consumer_info(settings.stream, settings.durable_consumer)
    except not_found_error:
        try:
            await jetstream.add_consumer(settings.stream, consumer_config)
        except api_error:
            # The durable is shared by all scheduler replicas in this run.
            await jetstream.consumer_info(settings.stream, settings.durable_consumer)
