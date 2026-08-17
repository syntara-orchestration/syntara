"""Integration tests for execution WebSocket streaming.

These tests verify the WebSocket streaming infrastructure for executions:
- Connection handling and validation
- Event replay from Redis Streams
- Message format validation
- Error handling for terminal executions

Note: Full end-to-end tests with Temporal worker are performed manually
using specs/024-execution-visualizer/workflow-stream-viewer.py

These tests require:
- PostgreSQL database
- Redis server

Run with: pytest tests/integration/workflows/test_execution_websocket_streaming.py
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from starlette.testclient import TestClient

from syntara.core.cache.stream import StreamClient
from tests.helpers.workflow import create_minimal_workflow_definition

pytestmark = pytest.mark.integration


# ============================================================================
# Helper Functions
# ============================================================================


def create_activity_patch_event(execution_id: UUID, activity_idx: int, status: str) -> dict[str, object]:
    """Create an activity_patch event."""
    return {
        "type": "activity_patch",
        "execution_id": str(execution_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "ops": [
            {
                "op": "replace",
                "path": f"/activities/{activity_idx}/status",
                "value": status,
            }
        ],
    }


def create_initial_snapshot_event(execution_id: UUID) -> dict[str, object]:
    """Create an initial_snapshot event."""
    return {
        "type": "initial_snapshot",
        "execution_id": str(execution_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "execution": {
            "id": str(execution_id),
            "status": "running",
            "activities": [
                {
                    "activity_id": "task1",
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "error_details": None,
                },
                {
                    "activity_id": "task2",
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "error_details": None,
                },
            ],
        },
    }


def create_final_snapshot_event(execution_id: UUID) -> dict[str, object]:
    """Create a final_snapshot event."""
    return {
        "type": "final_snapshot",
        "execution_id": str(execution_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "execution": {
            "id": str(execution_id),
            "status": "completed",
            "activities": [
                {
                    "activity_id": "task1",
                    "status": "completed",
                    "started_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error_details": None,
                },
                {
                    "activity_id": "task2",
                    "status": "completed",
                    "started_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error_details": None,
                },
            ],
        },
    }


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def test_execution_stream() -> AsyncGenerator[tuple[UUID, str], None]:
    """Fixture providing execution stream with auto-cleanup."""
    execution_id = uuid4()
    stream_id = f"execution:{execution_id}:events"

    yield execution_id, stream_id

    # Cleanup: Delete stream after test
    async with StreamClient() as client:
        try:
            await client.delete(stream_id)
        except Exception:
            pass  # Stream may not exist


@pytest_asyncio.fixture
async def populated_execution_stream(
    test_execution_stream: tuple[UUID, str],
) -> tuple[UUID, str, list[str]]:
    """Stream with pre-populated execution events."""
    execution_id, stream_id = test_execution_stream

    async with StreamClient() as client:
        event_ids = []

        # Publish initial snapshot
        event_id = await client.publish(stream_id, create_initial_snapshot_event(execution_id))
        event_ids.append(event_id)

        # Publish activity patch events
        event_id = await client.publish(stream_id, create_activity_patch_event(execution_id, 0, "running"))
        event_ids.append(event_id)

        event_id = await client.publish(stream_id, create_activity_patch_event(execution_id, 0, "completed"))
        event_ids.append(event_id)

        event_id = await client.publish(stream_id, create_activity_patch_event(execution_id, 1, "running"))
        event_ids.append(event_id)

        event_id = await client.publish(stream_id, create_activity_patch_event(execution_id, 1, "completed"))
        event_ids.append(event_id)

        # Publish final snapshot
        event_id = await client.publish(stream_id, create_final_snapshot_event(execution_id))
        event_ids.append(event_id)

    return execution_id, stream_id, event_ids


@pytest_asyncio.fixture
async def test_execution(jwt_client: AsyncClient) -> UUID:
    """Create a test execution in the database."""
    # Create a minimal workflow first
    workflow_response = await jwt_client.post(
        "/api/v1/workflows",
        json={
            "name": "test-streaming-workflow",
            "workflow_definition": create_minimal_workflow_definition(
                name="test-streaming",
                description="Test streaming workflow",
                activity_id="task1",
            ),
        },
    )
    assert workflow_response.status_code == 201, f"Failed to create workflow: {workflow_response.text}"
    workflow = workflow_response.json()

    # Create an execution
    execution_response = await jwt_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": workflow["id"],
            "input_data": {},
        },
    )
    assert execution_response.status_code == 201, f"Failed to create execution: {execution_response.text}"
    execution = execution_response.json()

    return UUID(execution["id"])


# ============================================================================
# WebSocket Streaming Tests
# ============================================================================


class TestExecutionWebSocketConnection:
    """Test WebSocket connection handling."""

    def test_invalid_execution_id_closes_connection(self, sync_test_client: TestClient) -> None:
        """Test that invalid execution ID closes connection with error."""
        with sync_test_client.websocket_connect("/ws/workflows/v1/executions/not-a-uuid") as websocket:
            # Expect connection to close with error
            close_event = websocket.receive()
            assert close_event["type"] == "websocket.close"
            assert close_event["code"] == 1003

    def test_nonexistent_execution_closes_connection(self, sync_test_client: TestClient) -> None:
        """Test that nonexistent execution ID closes connection with error."""
        fake_execution_id = uuid4()
        with sync_test_client.websocket_connect(f"/ws/workflows/v1/executions/{fake_execution_id}") as websocket:
            # Should receive error event first
            event = websocket.receive_json()
            assert event["event_type"] == "error"
            assert "EXECUTION_NOT_FOUND" in event["data"]["code"]

            # Then connection should close (POLICY_VIOLATION = 1008)
            close_event = websocket.receive()
            assert close_event["type"] == "websocket.close"
            assert close_event["code"] == 1008
