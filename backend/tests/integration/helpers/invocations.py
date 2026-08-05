"""Helper functions for Invocations."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from httpx import AsyncClient


@asynccontextmanager
async def wait_for_invocation_execution(
    client: AsyncClient, invocation_id: str, max_wait_time: float = 5.0, wait_interval: float = 0.1
) -> AsyncGenerator[dict[str, Any] | None, None]:
    """Context manager that waits for an invocation to start execution.

    This ensures that tests can treat invocation creation as if it were synchronous,
    even though execution happens in background tasks.

    Args:
        client: The HTTP client to use for polling
        invocation_id: The ID of the invocation to monitor
        max_wait_time: Maximum time to wait in seconds (default: 5.0)
        wait_interval: How often to check in seconds (default: 0.1)

    Yields:
        The final invocation data after execution has started or timeout

    """
    elapsed_time = 0.0
    final_data: dict[str, Any] | None = None

    while elapsed_time < max_wait_time:
        # Check the current status of the invocation
        status_response = await client.get(f"/_internal/invocations/{invocation_id}")
        if status_response.status_code == 200:
            status_data = status_response.json()
            if status_data["status"] in ["completed", "failed"]:
                final_data = status_data
                break

        await asyncio.sleep(wait_interval)
        elapsed_time += wait_interval

    # If we didn't get execution state, get the current state for testing
    if final_data is None:
        status_response = await client.get(f"/_internal/invocations/{invocation_id}")
        if status_response.status_code == 200:
            final_data = status_response.json()

    yield final_data
