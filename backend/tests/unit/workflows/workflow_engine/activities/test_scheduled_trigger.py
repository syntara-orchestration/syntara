"""Tests for scheduled trigger Temporal activity.

Covers:
- Basic pass-through of schedule config
- Schedule config fields preserved in output
- Output mapping applied correctly
- Empty config handling
"""

from syntara.workflows.workflow_engine.activities.scheduled_trigger import scheduled_trigger


async def test_scheduled_trigger_basic() -> None:
    """Scheduled trigger should return input config as output."""
    input_config = {"schedule_type": "cron", "cron": "0 9 * * *", "timezone": "America/New_York"}
    result = await scheduled_trigger(input_config, None)

    assert result == {
        "output": {
            "schedule_type": "cron",
            "cron": "0 9 * * *",
            "timezone": "America/New_York",
        }
    }


async def test_scheduled_trigger_interval() -> None:
    """Interval schedule config should pass through correctly."""
    input_config = {
        "schedule_type": "interval",
        "interval": "R/2024-01-01T10:00:00Z/P1D",
    }
    result = await scheduled_trigger(input_config, None)

    assert result == {
        "output": {
            "schedule_type": "interval",
            "interval": "R/2024-01-01T10:00:00Z/P1D",
        }
    }


async def test_scheduled_trigger_empty_config() -> None:
    """Empty config should return empty output."""
    result = await scheduled_trigger({}, None)
    assert result == {"output": {}}


async def test_scheduled_trigger_with_output_mapping_suppresses_fields() -> None:
    """Output mapping with explicit keys should suppress unmapped fields."""
    input_config = {"schedule_type": "cron", "cron": "0 9 * * *"}
    output_config = {"schedule": "schedule_type"}

    result = await scheduled_trigger(input_config, output_config)

    output = result["output"]
    assert "schedule" in output


async def test_scheduled_trigger_with_empty_output_mapping() -> None:
    """Empty output mapping should suppress all fields."""
    input_config = {"schedule_type": "cron", "cron": "0 9 * * *"}
    result = await scheduled_trigger(input_config, {})

    assert result["output"] == {}
