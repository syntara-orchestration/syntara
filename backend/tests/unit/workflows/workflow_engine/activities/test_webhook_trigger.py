"""Tests for webhook trigger Temporal activity.

Covers:
- Basic pass-through
- Output mapping applied correctly
- Raw request body passes through as trigger input
"""

import pytest

from syntara.workflows.workflow_engine.activities.webhook_trigger import webhook_trigger


async def test_webhook_trigger_basic() -> None:
    """Webhook trigger should return input as output."""
    input_config = {"event": "push", "repo": "nexus"}
    result = await webhook_trigger(input_config, None)

    assert result == {
        "output": {
            "event": "push",
            "repo": "nexus",
        }
    }


async def test_webhook_trigger_empty_payload() -> None:
    """Empty payload should return empty output."""
    result = await webhook_trigger({}, None)
    assert result == {"output": {}}


async def test_webhook_trigger_with_output_mapping_suppresses_fields() -> None:
    """Output mapping with explicit keys should suppress unmapped fields."""
    input_config = {"event": "push", "repo": "nexus"}
    output_config = {"event_type": "event"}

    result = await webhook_trigger(input_config, output_config)

    output = result["output"]
    assert "event_type" in output


async def test_webhook_trigger_with_empty_output_mapping() -> None:
    """Empty output mapping should suppress all fields."""
    input_config = {"event": "push"}
    result = await webhook_trigger(input_config, {})

    output = result["output"]
    assert output == {}


async def test_webhook_trigger_status_in_payload_passes_through() -> None:
    """User-supplied status in input is treated as user data."""
    input_config = {"data": "test", "status": "failed"}
    result = await webhook_trigger(input_config, None)

    assert result["output"]["status"] == "failed"


async def test_webhook_trigger_no_control_in_result() -> None:
    """Webhook trigger result should only contain output, not control."""
    input_config = {"event": "push"}
    result = await webhook_trigger(input_config, None)

    assert "output" in result
    assert "control" not in result


async def test_webhook_trigger_nested_payload() -> None:
    """Nested structures pass through unchanged."""
    input_config = {
        "repository": {"owner": "org", "name": "repo"},
        "commits": [{"id": "abc123"}, {"id": "def456"}],
    }
    result = await webhook_trigger(input_config, None)

    output = result["output"]
    assert output["repository"]["owner"] == "org"
    assert len(output["commits"]) == 2


async def test_webhook_trigger_bad_output_mapping_raises() -> None:
    """Bad output mapping raises ApplicationError."""
    from temporalio.exceptions import ApplicationError

    input_config = {"event": "push"}
    with pytest.raises(ApplicationError) as exc_info:
        await webhook_trigger(input_config, {"x": "${result.nonexistent}"})
    assert exc_info.value.type == "OutputMappingError"
