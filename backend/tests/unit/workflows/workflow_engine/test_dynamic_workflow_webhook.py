"""Tests for ALLOWED_TRIGGER_TYPES in dynamic_workflow."""

from syntara.workflow_runtime.engines.temporal.dynamic_workflow import ALLOWED_TRIGGER_TYPES
from syntara.workflow_runtime.engines.temporal.models.workflow_definition import ActivityName


async def test_allowed_trigger_types_are_valid_triggers() -> None:
    """ALLOWED_TRIGGER_TYPES must only contain trigger activity names."""
    trigger_activity_names = {
        ActivityName.MANUAL_TRIGGER,
        ActivityName.SCHEDULED_TRIGGER,
        ActivityName.WEBHOOK_TRIGGER,
        ActivityName.EDA_TRIGGER,
    }
    assert trigger_activity_names >= ALLOWED_TRIGGER_TYPES
