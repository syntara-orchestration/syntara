"""Event triggers use ordinary output mapping without transport operations."""

import copy
from typing import Any
from unittest.mock import patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.event_subscribe_trigger import event_subscribe_trigger
from syntara.workflows.workflow_engine.activities.registry import ACTIVITY_REGISTRY, BACKGROUND_ACTIVITY_REGISTRY
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.services.activity_sync_event_processor import ActivitySyncEventProcessorMixin


@pytest.fixture
def envelope() -> dict[str, Any]:
    """An already supplied envelope; transport metadata remains opaque."""
    return {
        "envelope_version": 1,
        "payload": {"secret": "CUSTOMER_PAYLOAD", "count": 2},
        "original": {"value_base64": "e30=", "key_base64": None, "headers": []},
        "cloudevents": None,
        "metadata": {"source_generation": 1, "offset": "9007199254740993"},
    }


@pytest.mark.parametrize("payload", [None, True, 3, "text", [1, {"nested": True}], {"status": "failed"}])
async def test_payload_types_pass_through(envelope: dict[str, Any], payload: Any) -> None:  # noqa: ANN401
    envelope["payload"] = payload
    before = copy.deepcopy(envelope)
    assert await event_subscribe_trigger(envelope, None) == {"output": before}
    assert envelope == before


async def test_mapping_and_suppression_preserve_source(envelope: dict[str, Any]) -> None:
    before = copy.deepcopy(envelope)
    assert await event_subscribe_trigger(envelope, {"count": "${result.payload.count}"}) == {"output": {"count": 2}}
    assert await event_subscribe_trigger(envelope, {}) == {"output": {}}
    assert envelope == before


async def test_invalid_mapping_preserves_source(envelope: dict[str, Any]) -> None:
    before = copy.deepcopy(envelope)
    with pytest.raises(ApplicationError, match="Failed to resolve output mapping"):
        await event_subscribe_trigger(envelope, {"missing": "${result.absent}"})
    assert envelope == before


async def test_no_payload_logging_or_workflow_launch(
    envelope: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    with patch("temporalio.workflow.start_child_workflow") as start_workflow:
        await event_subscribe_trigger(envelope, None)
    start_workflow.assert_not_called()
    assert "CUSTOMER_PAYLOAD" not in caplog.text
    assert "e30=" not in caplog.text


def test_registry_and_sync_wiring() -> None:
    assert ACTIVITY_REGISTRY[ActivityName.EVENT_SUBSCRIBE_TRIGGER] is event_subscribe_trigger
    assert ActivityName.EVENT_SUBSCRIBE_TRIGGER not in BACKGROUND_ACTIVITY_REGISTRY
    assert (
        ActivitySyncEventProcessorMixin._extract_trigger_activity_type(
            {"incoming": {"type": "event_subscribe_trigger"}}
        )
        == ActivityName.EVENT_SUBSCRIBE_TRIGGER
    )
