"""Default handler registry + a reference workflow-launch handler.

The reference handler adapts a :class:`WorkflowLauncher` into the registry's
``MessageHandlerFn`` shape. The launcher is the Temporal handoff seam: swap the
:class:`LoggingWorkflowLauncher` default for one wrapping the real execution
service without touching the runtime or the pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.eventstreams.core.registry import HandlerRegistry, MessageHandlerFn

if TYPE_CHECKING:
    from syntara.eventstreams.core.envelope import EventEnvelope
    from syntara.eventstreams.core.handler import WorkflowLauncher

logger = structlog.stdlib.get_logger(__name__)


class LoggingWorkflowLauncher:
    """A no-op :class:`WorkflowLauncher` that logs instead of starting a workflow.

    Lets the consumer run end-to-end (receive -> filter -> "handoff" -> commit)
    without the full execution service wired in. Implements the protocol
    structurally.
    """

    async def launch(self, envelope: EventEnvelope, payload: object) -> str | None:  # noqa: ARG002
        """Log the message instead of starting a workflow; always returns ``None``."""
        logger.info(
            "eventstream_workflow_launch_stub",
            message_id=envelope.message_id,
            source=envelope.source,
            event_type=envelope.event_type,
        )
        return None


def make_workflow_launch_handler(launcher: WorkflowLauncher) -> MessageHandlerFn:
    """Adapt a :class:`WorkflowLauncher` into a registry ``MessageHandlerFn``.

    A :class:`TransientHandlerError` raised by ``launcher.launch`` propagates so
    the pipeline classifies it as RETRY; all other exceptions are treated as
    permanent (ACK) upstream so a partition is never blocked.
    """

    async def _handle(envelope: EventEnvelope, payload: object) -> None:
        await launcher.launch(envelope, payload)

    return _handle


def build_default_registry(launcher: WorkflowLauncher | None = None) -> HandlerRegistry:
    """Registry whose default handler forwards every message to a workflow launch.

    With no ``event_type`` routing configured yet, all messages fall through to
    the default handler (ANSTRAT-1934 will add typed routing later).
    """
    handler = make_workflow_launch_handler(launcher or LoggingWorkflowLauncher())
    return HandlerRegistry(default=handler)
