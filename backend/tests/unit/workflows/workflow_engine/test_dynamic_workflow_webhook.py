"""Tests for ALLOWED_TRIGGER_TYPES in dynamic_workflow."""

from syntara.workflows.workflow_engine.dynamic_workflow import ALLOWED_TRIGGER_TYPES
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName


async def test_allowed_trigger_types_are_valid_triggers() -> None:
    """ALLOWED_TRIGGER_TYPES must only contain trigger activity names."""
    trigger_activity_names = {
        ActivityName.MANUAL_TRIGGER,
        ActivityName.SCHEDULED_TRIGGER,
        ActivityName.WEBHOOK_TRIGGER,
        ActivityName.EDA_TRIGGER,
    }
    assert trigger_activity_names >= ALLOWED_TRIGGER_TYPES
