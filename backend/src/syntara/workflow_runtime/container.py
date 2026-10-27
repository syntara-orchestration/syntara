"""Execution boundary for activities that run outside the worker process.

The runtime depends on this small protocol rather than an OpenShift or
Kubernetes SDK. A deployment can provide an OpenShift implementation; tests
and local development can inject a fake.
"""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from syntara.workflow_runtime.contracts import ActivityContext, ActivityError, Completed, Deferred

ActivityOutcome = Completed | Deferred


@dataclass(frozen=True)
class ContainerExecutionRequest:
    """Portable request passed from the activity adapter to a container runner."""

    activity_name: str
    activity_version: int
    execution_id: UUID
    node_execution_id: str
    input: dict[str, Any]
    image: str
    timeout_seconds: int


class ContainerExecutor(Protocol):
    """Launch and collect one executor activity outside the worker process."""

    async def run(self, request: ContainerExecutionRequest, context: ActivityContext) -> ActivityOutcome:
        """Run a container and return a neutral activity outcome."""


class OpenShiftContainerExecutor:
    """Placeholder for the OpenShift execution-plane integration."""

    async def run(self, request: ContainerExecutionRequest, context: ActivityContext) -> ActivityOutcome:
        """Fail explicitly until an OpenShift client is configured."""
        del context
        message = f"Container execution is not configured for {request.activity_name}@{request.activity_version}"
        raise ActivityError(message, code="ContainerExecutorUnavailable", retryable=True)
