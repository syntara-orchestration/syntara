"""Unit tests for the public shape of ActivityExecution."""

from syntara.workflows.models.activity_execution import ActivityExecution


def test_control_data_is_excluded_from_activity_api_serialization() -> None:
    """Internal routing state must not change the public ActivityExecution contract."""
    activity = ActivityExecution.model_construct(control_data={"next_port": "true"})

    assert "control_data" not in activity.model_dump()
