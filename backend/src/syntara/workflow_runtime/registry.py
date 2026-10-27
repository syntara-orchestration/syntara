"""Explicit, versioned registration of business activity handlers."""

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from syntara.workflow_runtime.contracts import ActivityContext, ActivityError, Completed, Deferred

type ActivityOutcome = Completed | Deferred
type ActivityHandler = Callable[[dict[str, Any], ActivityContext], ActivityOutcome | Awaitable[ActivityOutcome]]
type ActivityExecutionMode = Literal["worker", "container"]


@dataclass(frozen=True)
class ActivityDefinition:
    """Immutable business registration; deployment routing belongs elsewhere."""

    name: str
    version: int
    handler: ActivityHandler
    supports_deferred: bool = False
    execution_mode: ActivityExecutionMode = "worker"
    container_image: str | None = None
    container_timeout_seconds: int = 300
    cancel_handler: ActivityHandler | None = None
    expire_handler: ActivityHandler | None = None

    def __post_init__(self) -> None:
        """Validate execution metadata at provider registration time."""
        if self.execution_mode == "container" and not self.container_image:
            msg = f"Container activity {self.name}@{self.version} requires an image"
            raise ValueError(msg)
        if self.container_timeout_seconds < 1:
            msg = "Container activity timeout must be positive"
            raise ValueError(msg)

    def validate_outcome(self, outcome: object, context: ActivityContext) -> ActivityOutcome:
        """Validate an outcome returned by either local or external execution."""
        if isinstance(outcome, Completed):
            json.dumps(outcome.output, allow_nan=False)
        elif isinstance(outcome, Deferred):
            if not self.supports_deferred or outcome.completion_ref != context.completion_ref:
                msg = "Handler returned an unauthorized completion reference"
                raise ActivityError(msg)
        else:
            msg = "Handler must return Completed or Deferred"
            raise ActivityError(msg)
        return outcome

    async def invoke(self, inputs: dict[str, Any], context: ActivityContext) -> ActivityOutcome:
        """Invoke either Python execution style without blocking the event loop."""
        return await self._invoke_handler(self.handler, inputs, context)

    async def invoke_lifecycle(
        self,
        operation: Literal["cancel", "expire"],
        inputs: dict[str, Any],
        context: ActivityContext,
    ) -> ActivityOutcome:
        """Invoke an optional cleanup hook for a deferred activity."""
        handler = self.cancel_handler if operation == "cancel" else self.expire_handler
        if handler is None:
            msg = f"Activity does not support lifecycle operation: {self.name}@{self.version} ({operation})"
            raise ActivityError(msg, code="UnsupportedActivityLifecycle")
        outcome = await self._invoke_handler(handler, inputs, context)
        if isinstance(outcome, Deferred):
            msg = f"Lifecycle operation cannot defer: {self.name}@{self.version} ({operation})"
            raise ActivityError(msg, code="InvalidActivityLifecycle")
        return outcome

    async def _invoke_handler(
        self,
        handler: ActivityHandler,
        inputs: dict[str, Any],
        context: ActivityContext,
    ) -> ActivityOutcome:
        """Invoke and validate a handler shared by execution and lifecycle hooks."""
        if inspect.iscoroutinefunction(handler):
            outcome = await handler(inputs, context)
        else:
            outcome = await asyncio.to_thread(handler, inputs, context)
            if inspect.isawaitable(outcome):
                outcome = await outcome
        return self.validate_outcome(outcome, context)


class ActivityRegistry:
    """Registry populated by worker composition, never by workflow replay."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._definitions: dict[tuple[str, int], ActivityDefinition] = {}

    def register(self, definition: ActivityDefinition) -> None:
        """Register one version, rejecting ambiguous or invalid registrations."""
        key = (definition.name, definition.version)
        if not definition.name or definition.version < 1 or key in self._definitions:
            msg = f"Invalid or duplicate activity registration: {key}"
            raise ValueError(msg)
        self._definitions[key] = definition

    def resolve(self, name: str, version: int) -> ActivityDefinition:
        """Resolve a pinned version or fail explicitly."""
        try:
            return self._definitions[name, version]
        except KeyError as exc:
            msg = f"Activity is not installed: {name}@{version}"
            raise ActivityError(msg, code="UnknownActivity") from exc
