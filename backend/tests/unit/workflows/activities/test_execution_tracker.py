"""Unit tests for activity execution tracking.

Tests the in-memory stub implementation of execution tracking that will be
replaced with database operations in Phase 3+.
"""

# PLR2004: Test assertions use literal values which is standard practice in unit tests.

import asyncio

import pytest

from syntara.workflows.workflow_engine.activities.execution_tracker import (
    cancel_execution_activities,
    clear_tracking_data,
    create_activity_execution,
    get_activity_execution,
    get_execution_activities,
    update_activity_execution,
)


class TestCreateActivityExecution:
    """Test creating activity execution records."""

    @pytest.mark.asyncio
    async def test_create_activity_execution_basic(self) -> None:
        """Test creating a basic activity execution record."""
        clear_tracking_data()

        result = await create_activity_execution(
            execution_id="exec-123",
            activity_id="task1",
            activity_name="Test Task",
        )

        assert result["id"] is not None
        assert result["execution_id"] == "exec-123"
        assert result["activity_id"] == "task1"
        assert result["activity_name"] == "Test Task"
        assert result["status"] == "running"
        assert result["input_data"] == {}
        assert result["output_data"] is None
        assert result["error_details"] is None
        assert result["retry_count"] == 0
        assert result["iteration"] is None
        assert result["started_at"] is not None
        assert result["completed_at"] is None

    @pytest.mark.asyncio
    async def test_create_activity_execution_with_input_data(self) -> None:
        """Test creating activity execution with input data."""
        clear_tracking_data()

        input_data = {"user_id": 123, "action": "fetch"}
        result = await create_activity_execution(
            execution_id="exec-456",
            activity_id="task2",
            activity_name="Fetch User",
            input_data=input_data,
        )

        assert result["input_data"] == input_data

    @pytest.mark.asyncio
    async def test_create_activity_execution_with_iteration(self) -> None:
        """Test creating activity execution with iteration number."""
        clear_tracking_data()

        result = await create_activity_execution(
            execution_id="exec-789",
            activity_id="loop_task",
            activity_name="Loop Task",
            iteration=5,
        )

        assert result["iteration"] == 5

    @pytest.mark.asyncio
    async def test_create_multiple_activity_executions(self) -> None:
        """Test creating multiple activity execution records."""
        clear_tracking_data()

        result1 = await create_activity_execution(
            execution_id="exec-multi",
            activity_id="task1",
            activity_name="Task 1",
        )

        result2 = await create_activity_execution(
            execution_id="exec-multi",
            activity_id="task2",
            activity_name="Task 2",
        )

        # Should have unique IDs
        assert result1["id"] != result2["id"]
        # Should both have same execution_id
        assert result1["execution_id"] == result2["execution_id"]


class TestUpdateActivityExecution:
    """Test updating activity execution records."""

    @pytest.mark.asyncio
    async def test_update_activity_execution_status(self) -> None:
        """Test updating activity execution status."""
        clear_tracking_data()

        # Create activity execution
        created = await create_activity_execution(
            execution_id="exec-update",
            activity_id="task1",
            activity_name="Test Task",
        )

        # Update status
        updated = await update_activity_execution(
            activity_exec_id=created["id"],
            status="completed",
        )

        assert updated["status"] == "completed"
        assert updated["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_activity_execution_output_data(self) -> None:
        """Test updating activity execution with output data."""
        clear_tracking_data()

        created = await create_activity_execution(
            execution_id="exec-update",
            activity_id="task1",
            activity_name="Test Task",
        )

        output_data = {"result": "success", "data": {"user": "John"}}
        updated = await update_activity_execution(
            activity_exec_id=created["id"],
            output_data=output_data,
        )

        assert updated["output_data"] == output_data

    @pytest.mark.asyncio
    async def test_update_activity_execution_error_details(self) -> None:
        """Test updating activity execution with error details."""
        clear_tracking_data()

        created = await create_activity_execution(
            execution_id="exec-update",
            activity_id="task1",
            activity_name="Test Task",
        )

        updated = await update_activity_execution(
            activity_exec_id=created["id"],
            status="failed",
            error_details="Connection timeout",
        )

        assert updated["status"] == "failed"
        assert updated["error_details"] == "Connection timeout"
        assert updated["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_activity_execution_retry_count(self) -> None:
        """Test updating activity execution retry count."""
        clear_tracking_data()

        created = await create_activity_execution(
            execution_id="exec-update",
            activity_id="task1",
            activity_name="Test Task",
        )

        updated = await update_activity_execution(
            activity_exec_id=created["id"],
            retry_count=3,
        )

        assert updated["retry_count"] == 3

    @pytest.mark.asyncio
    async def test_update_activity_execution_multiple_fields(self) -> None:
        """Test updating multiple fields at once."""
        clear_tracking_data()

        created = await create_activity_execution(
            execution_id="exec-update",
            activity_id="task1",
            activity_name="Test Task",
        )

        updated = await update_activity_execution(
            activity_exec_id=created["id"],
            status="completed",
            output_data={"result": "done"},
            retry_count=1,
        )

        assert updated["status"] == "completed"
        assert updated["output_data"] == {"result": "done"}
        assert updated["retry_count"] == 1
        assert updated["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_activity_execution_cancelled_status(self) -> None:
        """Test updating activity execution to cancelled status."""
        clear_tracking_data()

        created = await create_activity_execution(
            execution_id="exec-update",
            activity_id="task1",
            activity_name="Test Task",
        )

        updated = await update_activity_execution(
            activity_exec_id=created["id"],
            status="cancelled",
        )

        assert updated["status"] == "cancelled"
        assert updated["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_activity_execution_not_found(self) -> None:
        """Test updating non-existent activity execution raises KeyError."""
        clear_tracking_data()

        with pytest.raises(KeyError, match="Activity execution not found"):
            await update_activity_execution(
                activity_exec_id="nonexistent-id",
                status="completed",
            )


class TestGetActivityExecution:
    """Test retrieving activity execution records."""

    @pytest.mark.asyncio
    async def test_get_activity_execution_success(self) -> None:
        """Test getting an activity execution by ID."""
        clear_tracking_data()

        created = await create_activity_execution(
            execution_id="exec-get",
            activity_id="task1",
            activity_name="Test Task",
        )

        retrieved = await get_activity_execution(created["id"])

        assert retrieved["id"] == created["id"]
        assert retrieved["execution_id"] == "exec-get"
        assert retrieved["activity_id"] == "task1"

    @pytest.mark.asyncio
    async def test_get_activity_execution_not_found(self) -> None:
        """Test getting non-existent activity execution raises KeyError."""
        clear_tracking_data()

        with pytest.raises(KeyError, match="Activity execution not found"):
            await get_activity_execution("nonexistent-id")


class TestGetExecutionActivities:
    """Test retrieving all activities for an execution."""

    @pytest.mark.asyncio
    async def test_get_execution_activities_empty(self) -> None:
        """Test getting activities for execution with no activities."""
        clear_tracking_data()

        activities = await get_execution_activities("exec-empty")

        assert activities == []

    @pytest.mark.asyncio
    async def test_get_execution_activities_single(self) -> None:
        """Test getting activities for execution with one activity."""
        clear_tracking_data()

        await create_activity_execution(
            execution_id="exec-single",
            activity_id="task1",
            activity_name="Task 1",
        )

        activities = await get_execution_activities("exec-single")

        assert len(activities) == 1
        assert activities[0]["activity_id"] == "task1"

    @pytest.mark.asyncio
    async def test_get_execution_activities_multiple(self) -> None:
        """Test getting activities for execution with multiple activities."""
        clear_tracking_data()

        await create_activity_execution(
            execution_id="exec-multi",
            activity_id="task1",
            activity_name="Task 1",
        )

        await create_activity_execution(
            execution_id="exec-multi",
            activity_id="task2",
            activity_name="Task 2",
        )

        await create_activity_execution(
            execution_id="exec-multi",
            activity_id="task3",
            activity_name="Task 3",
        )

        activities = await get_execution_activities("exec-multi")

        assert len(activities) == 3
        activity_ids = {act["activity_id"] for act in activities}
        assert activity_ids == {"task1", "task2", "task3"}

    @pytest.mark.asyncio
    async def test_get_execution_activities_filters_by_execution_id(self) -> None:
        """Test that get_execution_activities only returns activities for specified execution."""
        clear_tracking_data()

        # Create activities for exec-1
        await create_activity_execution(
            execution_id="exec-1",
            activity_id="task1",
            activity_name="Task 1",
        )

        await create_activity_execution(
            execution_id="exec-1",
            activity_id="task2",
            activity_name="Task 2",
        )

        # Create activities for exec-2
        await create_activity_execution(
            execution_id="exec-2",
            activity_id="task3",
            activity_name="Task 3",
        )

        # Get activities for exec-1
        activities = await get_execution_activities("exec-1")

        assert len(activities) == 2
        activity_ids = {act["activity_id"] for act in activities}
        assert activity_ids == {"task1", "task2"}


class TestCancelExecutionActivities:
    """Test cancelling running activities for an execution."""

    @pytest.mark.asyncio
    async def test_cancel_execution_activities_none_running(self) -> None:
        """Test cancelling when no activities are running."""
        clear_tracking_data()

        count = await cancel_execution_activities("exec-cancel")

        assert count == 0

    @pytest.mark.asyncio
    async def test_cancel_execution_activities_single(self) -> None:
        """Test cancelling a single running activity."""
        clear_tracking_data()

        created = await create_activity_execution(
            execution_id="exec-cancel",
            activity_id="task1",
            activity_name="Task 1",
        )

        count = await cancel_execution_activities("exec-cancel")

        assert count == 1

        # Verify activity was marked as cancelled
        updated = await get_activity_execution(created["id"])
        assert updated["status"] == "cancelled"
        assert updated["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_cancel_execution_activities_multiple(self) -> None:
        """Test cancelling multiple running activities."""
        clear_tracking_data()

        task1 = await create_activity_execution(
            execution_id="exec-cancel",
            activity_id="task1",
            activity_name="Task 1",
        )

        task2 = await create_activity_execution(
            execution_id="exec-cancel",
            activity_id="task2",
            activity_name="Task 2",
        )

        task3 = await create_activity_execution(
            execution_id="exec-cancel",
            activity_id="task3",
            activity_name="Task 3",
        )

        count = await cancel_execution_activities("exec-cancel")

        assert count == 3

        # Verify all were cancelled
        for task in [task1, task2, task3]:
            updated = await get_activity_execution(task["id"])
            assert updated["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_execution_activities_only_running(self) -> None:
        """Test that only running activities are cancelled, not completed ones."""
        clear_tracking_data()

        # Create running activity
        running = await create_activity_execution(
            execution_id="exec-cancel",
            activity_id="task1",
            activity_name="Task 1",
        )

        # Create completed activity
        completed = await create_activity_execution(
            execution_id="exec-cancel",
            activity_id="task2",
            activity_name="Task 2",
        )
        await update_activity_execution(
            activity_exec_id=completed["id"],
            status="completed",
        )

        # Create failed activity
        failed = await create_activity_execution(
            execution_id="exec-cancel",
            activity_id="task3",
            activity_name="Task 3",
        )
        await update_activity_execution(
            activity_exec_id=failed["id"],
            status="failed",
        )

        # Cancel should only affect running activity
        count = await cancel_execution_activities("exec-cancel")

        assert count == 1

        # Verify only running was cancelled
        running_updated = await get_activity_execution(running["id"])
        assert running_updated["status"] == "cancelled"

        # Completed and failed should remain unchanged
        completed_updated = await get_activity_execution(completed["id"])
        assert completed_updated["status"] == "completed"

        failed_updated = await get_activity_execution(failed["id"])
        assert failed_updated["status"] == "failed"

    @pytest.mark.asyncio
    async def test_cancel_execution_activities_different_executions(self) -> None:
        """Test that cancel only affects activities from specified execution."""
        clear_tracking_data()

        # Create activities for exec-1
        exec1_task = await create_activity_execution(
            execution_id="exec-1",
            activity_id="task1",
            activity_name="Task 1",
        )

        # Create activities for exec-2
        exec2_task = await create_activity_execution(
            execution_id="exec-2",
            activity_id="task2",
            activity_name="Task 2",
        )

        # Cancel exec-1
        count = await cancel_execution_activities("exec-1")

        assert count == 1

        # Verify only exec-1 task was cancelled
        exec1_updated = await get_activity_execution(exec1_task["id"])
        assert exec1_updated["status"] == "cancelled"

        # exec-2 task should still be running
        exec2_updated = await get_activity_execution(exec2_task["id"])
        assert exec2_updated["status"] == "running"


class TestClearTrackingData:
    """Test clearing in-memory tracking data."""

    def test_clear_tracking_data(self) -> None:
        """Test that clear_tracking_data removes all data."""
        # This is a synchronous function
        clear_tracking_data()

        # After clearing, there should be no data
        # We can't directly access _activity_executions from here,
        # but we can verify by trying to get activities
        async def verify_empty() -> None:
            activities = await get_execution_activities("any-execution")
            assert activities == []

        asyncio.run(verify_empty())
