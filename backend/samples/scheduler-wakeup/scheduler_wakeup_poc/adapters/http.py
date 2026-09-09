"""HTTP transport and in-process receiver for the scheduler wake-up PoC.

The HTTP response only says that a Scheduler process set an in-memory pending
flag.  The execution store remains the source of truth for available work.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI, HTTPException, status
from sqlmodel import SQLModel

from scheduler_wakeup_poc.contracts import PublishReceipt, WakeHint, WakePublisher

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from scheduler_wakeup_poc.contracts import Scheduler


class WakePublishError(RuntimeError):
    """Raised when a wake-up was not accepted by the HTTP receiver."""


class WakeProtocolError(WakePublishError):
    """Raised when the remote receiver rejects a WakeHint as invalid."""


class WakeAcceptance(SQLModel):
    """Response from the internal HTTP receiver."""

    acceptance: str


class SchedulerWakeReceiver:
    """Coalesces valid wake hints and drains each configured queue.

    One receiver must live in the same process as its Scheduler.  Its flags
    are intentionally process-local, which is why a successful HTTP response
    has ``volatile`` acceptance semantics.
    """

    def __init__(
        self,
        scheduler: Scheduler,
        configured_queues: Iterable[str],
        *,
        retry_delay_seconds: float = 0.1,
    ) -> None:
        """Store the local Scheduler and its finite set of accepted queues."""
        queues = frozenset(configured_queues)
        if not queues:
            message = "SchedulerWakeReceiver needs at least one configured queue"
            raise ValueError(message)
        if any(not queue for queue in queues):
            message = "configured queues must be non-empty"
            raise ValueError(message)
        if retry_delay_seconds < 0:
            message = "retry_delay_seconds must be non-negative"
            raise ValueError(message)

        self._scheduler = scheduler
        self._queues = queues
        self._events = {queue: asyncio.Event() for queue in queues}
        self._retry_delay_seconds = retry_delay_seconds
        self._drain_tasks: dict[str, asyncio.Task[None]] = {}
        self._accepting = False
        self._closed = False

    @property
    def configured_queues(self) -> frozenset[str]:
        """Queues whose hints this process may accept."""
        return self._queues

    @property
    def accepting(self) -> bool:
        """Whether this process can currently accept volatile wake hints."""
        return self._accepting and not self._closed

    async def start(self) -> None:
        """Start one drain loop for each configured queue."""
        if self._closed:
            message = "cannot restart a closed SchedulerWakeReceiver"
            raise RuntimeError(message)
        if self._accepting:
            return

        self._accepting = True
        self._drain_tasks = {
            queue: asyncio.create_task(self._drain(queue), name=f"scheduler-wake-drain:{queue}")
            for queue in self._queues
        }

    async def close(self) -> None:
        """Stop drain loops without claiming any additional work."""
        if self._closed:
            return

        self._accepting = False
        self._closed = True
        for task in self._drain_tasks.values():
            task.cancel()
        if self._drain_tasks:
            await asyncio.gather(*self._drain_tasks.values(), return_exceptions=True)
        self._drain_tasks.clear()

    def accept(self, hint: WakeHint) -> PublishReceipt:
        """Set the queue's pending flag after validating receiver readiness."""
        if not self.accepting:
            message = "scheduler receiver is unavailable"
            raise WakePublishError(message)
        try:
            event = self._events[hint.queue]
        except KeyError as error:
            message = f"queue is not configured on this Scheduler: {hint.queue}"
            raise WakeProtocolError(message) from error

        event.set()
        return PublishReceipt(acceptance="volatile", transport_ref=str(hint.event_id))

    async def _drain(self, queue: str) -> None:
        """Run bounded passes until no immediate progress remains.

        Clearing before querying is deliberate: an arriving hint during a pass
        leaves the event set, so the next outer iteration cannot miss it.
        """
        event = self._events[queue]
        while True:
            await event.wait()
            event.clear()
            while self.accepting:
                try:
                    result = await self._scheduler.run_pass(queue)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - the Scheduler Protocol has no common failure base class.
                    # Keep the hint pending so a transient scheduling error
                    # cannot turn into a missed wake-up.
                    event.set()
                    await asyncio.sleep(self._retry_delay_seconds)
                    break

                if not result.immediate_more:
                    break
                # Yield so a long backlog does not monopolize this process.
                await asyncio.sleep(0)

class HTTPWakePublisher(WakePublisher):
    """Publishes volatile wake hints to a Scheduler HTTP endpoint."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        """Configure the Scheduler service base URL and request timeout."""
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def publish(self, hint: WakeHint) -> PublishReceipt:
        """Publish one hint and return only after the receiver sets its flag."""
        if self._client is not None:
            return await self._publish_with_client(self._client, hint)
        timeout = httpx.Timeout(self._timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await self._publish_with_client(client, hint)

    async def _publish_with_client(self, client: httpx.AsyncClient, hint: WakeHint) -> PublishReceipt:
        try:
            response = await client.post(
                f"{self._base_url}/internal/v1/scheduler/wake",
                json=hint.model_dump(mode="json"),
            )
        except httpx.HTTPError as error:
            message = f"HTTP wake-up request failed: {error}"
            raise WakePublishError(message) from error

        if response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
            message = f"HTTP receiver rejected wake hint: {response.text}"
            raise WakeProtocolError(message)
        if response.status_code != status.HTTP_202_ACCEPTED:
            message = f"HTTP receiver returned {response.status_code}: {response.text}"
            raise WakePublishError(message)

        try:
            body = WakeAcceptance.model_validate(response.json())
        except (TypeError, ValueError) as error:
            message = "HTTP receiver returned an invalid acceptance response"
            raise WakePublishError(message) from error
        if body.acceptance != "volatile":
            message = f"HTTP receiver returned unsupported acceptance: {body.acceptance}"
            raise WakePublishError(message)
        return PublishReceipt(acceptance="volatile", transport_ref=str(hint.event_id))


def create_scheduler_wake_app(receiver: SchedulerWakeReceiver) -> FastAPI:
    """Create a sample-only app that shares ``receiver`` with its Scheduler."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await receiver.start()
        try:
            yield
        finally:
            await receiver.close()

    app = FastAPI(title="Scheduler wake-up PoC", lifespan=lifespan)

    @app.post(
        "/internal/v1/scheduler/wake",
        response_model=WakeAcceptance,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def wake_scheduler(hint: WakeHint) -> WakeAcceptance:
        """Accept a validated volatile signal for a locally configured queue."""
        try:
            receipt = receiver.accept(hint)
        except WakeProtocolError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        except WakePublishError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        return WakeAcceptance(acceptance=receipt.acceptance)

    return app
