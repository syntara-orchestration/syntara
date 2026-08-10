"""Concurrency tests for tool management operations.

Tests concurrent operations to verify no deadlocks occur with:
- Concurrent bulk updates
- Concurrent individual updates
- Mixed concurrent operations

Addresses T011 requirement: "Test concurrent operations don't cause deadlocks"
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.dependencies import get_current_user
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.tool_manager.models import Tool

if TYPE_CHECKING:
    from tests.integration.helpers.tool_manager import ToolFactory


@pytest_asyncio.fixture
async def concurrency_client(test_db_engine, test_user: User, session_app) -> AsyncGenerator[AsyncClient, None]:
    """Client for concurrency testing that creates a new DB session for each request.

    Unlike base_client which shares a single session, this allows concurrent requests
    to each get their own session, preventing SQLAlchemy session conflicts.

    Uses session_app to ensure router discovery has been completed.

    See https://docs.sqlalchemy.org/en/20/errors.html#illegalstatechangeerror-and-concurrency-exceptions
    """

    # Override get_db to create a new session for each request
    async def get_db_for_concurrency() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(test_db_engine, expire_on_commit=False) as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    # Override get_current_user for authentication - use existing test_user
    async def get_test_user() -> "User":
        return test_user

    # Store original overrides to restore later
    original_overrides = dict(session_app.dependency_overrides)

    # Apply dependency overrides
    session_app.dependency_overrides[get_db] = get_db_for_concurrency
    session_app.dependency_overrides[get_current_user] = get_test_user

    try:
        async with AsyncClient(transport=ASGITransport(app=session_app), base_url="http://testserver") as client:
            yield client
    finally:
        # Restore original overrides
        session_app.dependency_overrides.clear()
        session_app.dependency_overrides.update(original_overrides)


@pytest_asyncio.fixture
async def simple_tools_for_concurrency(tool_factory: "ToolFactory") -> list[Tool]:
    """Create a few test tools for simple concurrency testing."""
    return await tool_factory.create_concurrency_tools(count=6)


class TestToolsConcurrency:
    """Concurrency tests for tool management operations."""

    @pytest.mark.asyncio
    async def test_concurrent_operations_complete_without_hanging(
        self, concurrency_client: AsyncClient, simple_tools_for_concurrency: list[Tool]
    ) -> None:
        """Test concurrent operations complete without hanging (no deadlocks)."""
        # Use different tools to avoid transaction conflicts that aren't deadlocks
        tool_ids_group1 = [str(tool.id) for tool in simple_tools_for_concurrency[:3]]
        tool_ids_group2 = [str(tool.id) for tool in simple_tools_for_concurrency[3:]]

        integration_id = simple_tools_for_concurrency[0].integration_id

        # Define concurrent bulk update operations on different tools
        async def bulk_update_group1() -> Response:
            return await concurrency_client.patch(
                f"/api/v1/integrations/{integration_id}/tools/bulk_update",
                json={"tool_ids": tool_ids_group1, "enabled": False},
            )

        async def bulk_update_group2() -> Response:
            return await concurrency_client.patch(
                f"/api/v1/integrations/{integration_id}/tools/bulk_update",
                json={"tool_ids": tool_ids_group2, "enabled": False},
            )

        start_time = time.time()

        # Execute concurrent bulk updates - should complete without hanging
        responses = await asyncio.gather(bulk_update_group1(), bulk_update_group2(), return_exceptions=True)

        end_time = time.time()

        # Main deadlock test: operations must complete in reasonable time
        execution_time = end_time - start_time
        assert execution_time < 10.0, f"Operations took {execution_time:.2f}s, possible deadlock or performance issue"

        # Verify operations completed and check response payloads
        for _, response in enumerate(responses):
            assert not isinstance(response, BaseException)
            assert response.status_code == 200

            # Verify response payload structure and counts
            data = response.json()
            assert "updated_count" in data
            assert "skipped_count" in data
            assert "updated_at" in data
            assert data["updated_count"] == 3  # Each group has 3 tools
            assert data["skipped_count"] == 0  # No tools should be skipped

        # GET all tools to verify final enabled states
        get_response = await concurrency_client.get("/api/v1/tools")
        assert get_response.status_code == 200

        tools_data = get_response.json()
        assert "resources" in tools_data
        assert len(tools_data["resources"]) == 6

        # Verify all tools are disabled (both groups were set to enabled=False)
        for tool in tools_data["resources"]:
            assert tool["enabled"] is False, f"Tool {tool['id']} should be disabled"

    @pytest.mark.asyncio
    async def test_multiple_concurrent_individual_updates_no_hang(
        self, concurrency_client: AsyncClient, simple_tools_for_concurrency: list[Tool]
    ) -> None:
        """Test multiple concurrent individual updates complete without hanging."""
        # Test concurrent individual updates on different tools
        tools_to_update = simple_tools_for_concurrency

        async def update_tool(tool: Tool, *, enabled: bool) -> Response:
            return await concurrency_client.patch(f"/api/v1/tools/{tool.id}", json={"enabled": enabled})

        # Create concurrent update tasks
        tasks = [update_tool(tool, enabled=i % 2 == 0) for i, tool in enumerate(tools_to_update)]

        start_time = time.time()

        # Execute concurrent individual updates
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()

        # Main test: no hanging (deadlock detection)
        execution_time = end_time - start_time
        assert execution_time < 10.0, f"Individual updates took {execution_time:.2f}s, possible deadlock"

        # Verify operations completed and check response payloads
        expected_enabled_states = []
        for i, response in enumerate(responses):
            assert not isinstance(response, BaseException)
            assert response.status_code == 200

            # Verify response payload structure for individual updates
            data = response.json()
            assert "id" in data
            assert "enabled" in data
            assert "updated_at" in data

            # Track expected final enabled state
            expected_enabled = i % 2 == 0
            expected_enabled_states.append((data["id"], expected_enabled))
            assert data["enabled"] == expected_enabled, f"Tool {data['id']} should have enabled={expected_enabled}"

        # GET all tools to verify final enabled states
        get_response = await concurrency_client.get("/api/v1/tools")
        assert get_response.status_code == 200

        tools_data = get_response.json()
        assert "resources" in tools_data
        assert len(tools_data["resources"]) == 6

        # Create lookup by tool ID and verify each tool has the expected enabled state
        tools_by_id = {tool["id"]: tool for tool in tools_data["resources"]}
        for tool_id, expected_enabled in expected_enabled_states:
            assert tool_id in tools_by_id, f"Tool {tool_id} not found in response"
            actual_enabled = tools_by_id[tool_id]["enabled"]
            assert actual_enabled == expected_enabled, (
                f"Tool {tool_id} expected enabled={expected_enabled}, got {actual_enabled}"
            )
