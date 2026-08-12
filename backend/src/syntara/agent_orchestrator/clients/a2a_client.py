"""A2A (Agent-to-Agent) protocol client for communicating with agent services."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable
from typing import Any
from uuid import UUID


class A2AClient(ABC):
    """Abstract base class for A2A protocol client.

    This interface will be used to communicate with distributed agent services
    via the A2A protocol. Currently mocked for NEXUS-002-1, will be implemented
    in NEXUS-002-4 when agent services are added.
    """

    @abstractmethod
    async def execute_task(
        self,
        agent_url: str,
        task: str,
        session_id: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterable[dict[str, Any]]:
        """Execute a task on an agent via A2A protocol.

        Args:
            agent_url: URL of the agent service (e.g., http://workflow-gen:8001)
            task: Natural language task description
            session_id: Session identifier for multi-tenant isolation
            context: Optional context data

        Yields:
            Progress events from the agent

        """

    @abstractmethod
    async def get_agent_status(self, agent_url: str, invocation_id: UUID) -> dict[str, Any]:
        """Get status of a running agent task.

        Args:
            agent_url: URL of the agent service
            invocation_id: Unique invocation identifier

        Returns:
            Agent status information

        """


class MockA2AClient(A2AClient):
    """Mock implementation of A2A client for NEXUS-002-1.

    This mock allows the API layer to be implemented with the correct abstractions
    while agent services are not yet deployed. Will be replaced with real
    httpx-based implementation in NEXUS-002-4.
    """

    async def execute_task(
        self,
        agent_url: str,
        task: str,  # noqa: ARG002
        session_id: str,
        context: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> AsyncIterable[dict[str, Any]]:
        """Mock task execution - yields placeholder events.

        Args:
            agent_url: URL of the agent service (unused in mock)
            task: Natural language task description
            session_id: Session identifier for multi-tenant isolation
            context: Optional context data

        Yields:
            Mock progress events

        """

        # Mock response - will be replaced with real A2A communication
        async def _mock_generator() -> AsyncIterable[dict[str, Any]]:
            yield {
                "type": "task_accepted",
                "session_id": session_id,
                "message": f"Mock: Task accepted by agent at {agent_url}",
            }

        return _mock_generator()

    async def get_agent_status(
        self,
        agent_url: str,  # noqa: ARG002
        invocation_id: UUID,
    ) -> dict[str, Any]:
        """Mock status check.

        Args:
            agent_url: URL of the agent service
            invocation_id: Unique invocation identifier

        Returns:
            Mock status information

        """
        return {
            "invocation_id": str(invocation_id),
            "status": "running",
            "message": "Mock: Agent is running",
        }
