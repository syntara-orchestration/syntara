"""Activity execution tracking for workflow monitoring.

This module provides functions to track activity execution progress in the database.
Activities call these functions before and after execution to record their state.

## Current Status: STUB IMPLEMENTATION (Phase 2)

This is a stub implementation using in-memory tracking. It provides the complete
API surface that will be used by the workflow engine, but stores data in memory
rather than in a database.

## Future Integration: Phase 3+ Database Implementation

### When This Will Be Used:

This module will be integrated into the workflow engine once the database layer
is implemented (see specs/003-workflow-engine/plan.md - Ticket 4: Execution Management).

### Required Database Models (from data-model.md):

```python
class Execution(Base):
    __tablename__ = "executions"

    id = Column(UUID, primary_key=True)
    workflow_version_id = Column(UUID, ForeignKey("workflow_versions.id"))
    status = Column(String)  # running, completed, failed, cancelled
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    input_data = Column(JSONB)
    output_data = Column(JSONB)
    error_details = Column(Text)
    triggered_by = Column(UUID, ForeignKey("users.id"))

class ActivityExecution(Base):
    __tablename__ = "activity_executions"

    id = Column(UUID, primary_key=True)
    execution_id = Column(UUID, ForeignKey("executions.id"))
    activity_id = Column(String)  # From YAML workflow definition
    activity_name = Column(String)
    status = Column(String)  # running, completed, failed, cancelled
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    input_data = Column(JSONB)
    output_data = Column(JSONB)
    error_details = Column(Text)
    retry_count = Column(Integer)
    iteration = Column(Integer)  # For loop activities
```

### How This Will Be Integrated:

In `dynamic_workflow.py`, the workflow engine will call these functions to track
activity execution:

```python
from syntara.workflows.activities import (
    create_activity_execution,
    update_activity_execution,
    cancel_execution_activities
)

async def _execute_task_activity(self, activity, execution_id, workflow_state):
    # Create activity execution record
    activity_exec = await create_activity_execution(
        execution_id=execution_id,
        activity_id=activity.id,
        activity_name=activity.name or activity.id,
        input_data=self._prepare_task_inputs(activity, workflow_state)
    )

    try:
        # Execute the activity
        result = await workflow.execute_activity(...)

        # Update with success
        await update_activity_execution(
            activity_exec_id=activity_exec["id"],
            status="completed",
            output_data=result
        )

    except Exception as e:
        # Update with failure
        await update_activity_execution(
            activity_exec_id=activity_exec["id"],
            status="failed",
            error_details=str(e)
        )
        raise
```

### Migration Path:

1. **Phase 3**: Implement database models using SQLAlchemy
2. **Replace in-memory storage**: Update this module to use `async def` with database operations
3. **Add database session management**: Pass SQLAlchemy async session to functions
4. **Integrate into workflow engine**: Add tracking calls in `dynamic_workflow.py`
5. **Add REST API endpoints**: Expose execution tracking via FastAPI
6. **Enable real-time monitoring**: WebSocket support for live execution status

### Benefits Once Integrated:

- **Persistent execution history**: Survive server restarts
- **Audit trail**: Complete record of all activity executions
- **Monitoring**: Real-time dashboards showing workflow progress
- **Debugging**: Detailed logs of what ran, when, and with what inputs/outputs
- **Retry tracking**: See how many times activities were retried
- **Cancellation support**: Properly mark activities as cancelled when workflows stop
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.stdlib.get_logger(__name__)

# In-memory storage for activity executions (stub for database)
_activity_executions: dict[str, dict[str, Any]] = {}


async def create_activity_execution(
    execution_id: str,
    activity_id: str,
    activity_name: str,
    input_data: dict[str, Any] | None = None,
    iteration: int | None = None,
) -> dict[str, Any]:
    """Create a new activity execution record.

    This function should be called at the start of activity execution.

    Args:
        execution_id: Parent workflow execution ID
        activity_id: Unique identifier for this activity within the workflow definition (from Activity.id)
        activity_name: Human-readable activity name
        input_data: Input parameters for the activity
        iteration: Iteration number for looped activities

    Returns:
        dict representing the activity execution record

    Example:
        >>> activity_exec = await create_activity_execution(
        ...     execution_id="exec-123",
        ...     activity_id="task1",
        ...     activity_name="Fetch User Data",
        ...     input_data={"user_id": 123}
        ... )

    """
    activity_exec_id = str(uuid4())

    activity_execution = {
        "id": activity_exec_id,
        "execution_id": execution_id,
        "activity_id": activity_id,
        "activity_name": activity_name,
        "input_data": input_data or {},
        "output_data": None,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "error_details": None,
        "retry_count": 0,
        "iteration": iteration,
    }

    # Store in memory (replace with database insert)
    _activity_executions[activity_exec_id] = activity_execution

    logger.info(
        "Created activity execution", activity_id=activity_id, execution_id=activity_exec_id, iteration=iteration
    )

    return activity_execution


async def update_activity_execution(
    activity_exec_id: str,
    status: str | None = None,
    output_data: dict[str, Any] | None = None,
    error_details: str | None = None,
    retry_count: int | None = None,
) -> dict[str, Any]:
    """Update an existing activity execution record.

    This function should be called after activity execution completes (success or failure).

    Args:
        activity_exec_id: Activity execution ID to update
        status: New status (completed, failed, cancelled)
        output_data: Output data from the activity
        error_details: Error message if activity failed
        retry_count: Number of retries attempted

    Returns:
        dict representing the updated activity execution record

    Raises:
        KeyError: If activity execution not found

    Example:
        >>> await update_activity_execution(
        ...     activity_exec_id="ae-456",
        ...     status="completed",
        ...     output_data={"user": {"id": 123, "name": "John"}}
        ... )

    """
    if activity_exec_id not in _activity_executions:
        msg = f"Activity execution not found: {activity_exec_id}"
        raise KeyError(msg)

    activity_execution = _activity_executions[activity_exec_id]

    # Update fields
    if status:
        activity_execution["status"] = status

    if output_data is not None:
        activity_execution["output_data"] = output_data

    if error_details is not None:
        activity_execution["error_details"] = error_details

    if retry_count is not None:
        activity_execution["retry_count"] = retry_count

    if status in ["completed", "failed", "cancelled"]:
        activity_execution["completed_at"] = datetime.now(UTC).isoformat()

    logger.info(
        "Updated activity execution",
        activity_exec_id=activity_exec_id,
        status=activity_execution["status"],
        retry_count=activity_execution["retry_count"],
    )

    return activity_execution


async def get_activity_execution(activity_exec_id: str) -> dict[str, Any]:
    """Get an activity execution record by ID.

    Args:
        activity_exec_id: Activity execution ID

    Returns:
        dict representing the activity execution record

    Raises:
        KeyError: If activity execution not found

    """
    if activity_exec_id not in _activity_executions:
        msg = f"Activity execution not found: {activity_exec_id}"
        raise KeyError(msg)

    return _activity_executions[activity_exec_id]


async def get_execution_activities(execution_id: str) -> list[dict[str, Any]]:
    """Get all activity executions for a workflow execution.

    Args:
        execution_id: Workflow execution ID

    Returns:
        list of activity execution records

    Example:
        >>> activities = await get_execution_activities("exec-123")
        >>> print(f"Found {len(activities)} activity executions")

    """
    return [
        activity_exec
        for activity_exec in _activity_executions.values()
        if activity_exec["execution_id"] == execution_id
    ]


async def cancel_execution_activities(execution_id: str) -> int:
    """Cancel all running activities for a workflow execution.

    This is called when a workflow is cancelled to mark all running activities as cancelled.

    Args:
        execution_id: Workflow execution ID

    Returns:
        int: Number of activities cancelled

    Example:
        >>> count = await cancel_execution_activities("exec-123")
        >>> print(f"Cancelled {count} activities")

    """
    cancelled_count = 0

    for activity_exec in _activity_executions.values():
        if activity_exec["execution_id"] == execution_id and activity_exec["status"] == "running":
            activity_exec["status"] = "cancelled"
            activity_exec["completed_at"] = datetime.now(UTC).isoformat()
            cancelled_count += 1

    logger.info(
        "Cancelled running activities for execution", cancelled_count=cancelled_count, execution_id=execution_id
    )

    return cancelled_count


def clear_tracking_data() -> None:
    """Clear all in-memory tracking data.

    This is primarily for testing purposes.
    """
    global _activity_executions  # noqa: PLW0603
    _activity_executions = {}
    logger.debug("Cleared all activity execution tracking data")
