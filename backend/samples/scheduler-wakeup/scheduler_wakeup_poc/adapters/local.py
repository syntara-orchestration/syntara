"""In-process reference adapter for the same drain-loop interface as HTTP."""

from __future__ import annotations

from ..contracts import PublishReceipt, WakeHint
from ..scheduler import WakeDrainLoop


class LocalWakePublisher:
    """Volatile local delivery used only when producer and receiver share a process."""

    def __init__(self, loop: WakeDrainLoop) -> None:
        self._loop = loop

    async def publish(self, hint: WakeHint) -> PublishReceipt:
        self._loop.wake(hint.queue)
        return PublishReceipt(acceptance="volatile", transport_ref=str(hint.event_id))
