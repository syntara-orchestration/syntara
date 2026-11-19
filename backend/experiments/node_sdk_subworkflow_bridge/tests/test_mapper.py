"""Phase 3: Control/Trigger → AO SubWorkflowExecutorParameters bridge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from node_sdk_subworkflow_bridge.mapper import (
    BridgeInjection,
    BridgeMappingError,
    map_control_to_ao_parameters,
    map_trigger_configuration_to_input_schema,
    qualified_workflow_from_control,
    wrap_sdk_output_as_ao_result,
)

from syntara.workflows.workflow_engine.models.workflow_definition import (
    SubWorkflowExecutorParameters,
    SubWorkflowOutputResult,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_map_control_requires_bridge_injection_for_uuid_and_trigger() -> None:
    control = _load("control.valid.json")
    injection = BridgeInjection(
        workflow_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        trigger_node_id="subworkflow_trigger_1",
        input_mapping={"artifact": "syntara-cli", "channel": "stable"},
    )
    params = map_control_to_ao_parameters(control, injection)
    assert isinstance(params, SubWorkflowExecutorParameters)
    assert params.workflow_id == injection.workflow_id
    assert params.trigger_node_id == injection.trigger_node_id
    assert params.input_mapping == injection.input_mapping
    assert qualified_workflow_from_control(control) == "acme.release.publish-artifact"


def test_map_control_rejects_missing_injection_uuid() -> None:
    control = _load("control.valid.json")
    with pytest.raises(BridgeMappingError, match="UUID"):
        map_control_to_ao_parameters(
            control,
            BridgeInjection(workflow_id="not-a-uuid", trigger_node_id="t1"),
        )


def test_map_control_rejects_non_control_document() -> None:
    trigger = _load("trigger.valid.json")
    with pytest.raises(BridgeMappingError, match="Control"):
        map_control_to_ao_parameters(
            trigger,
            BridgeInjection(
                workflow_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                trigger_node_id="t1",
            ),
        )


def test_trigger_configuration_becomes_ao_input_schema() -> None:
    trigger = _load("trigger.valid.json")
    schema = map_trigger_configuration_to_input_schema(trigger)
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"artifact", "channel"}


def test_sdk_business_result_wraps_into_ao_output_model() -> None:
    wrapped = wrap_sdk_output_as_ao_result(
        {"releaseId": "stable:cli", "publishedAt": "2026-01-01T00:00:00Z"},
        child_execution_id="11111111-1111-1111-1111-111111111111",
        child_workflow_id="22222222-2222-2222-2222-222222222222",
        child_workflow_name="publish-artifact",
        child_workflow_version=2,
        terminal_step_id="publish_artifact",
    )
    result = SubWorkflowOutputResult.model_validate(wrapped)
    assert result.child_status is not None
    assert result.child_status.value == "completed"
    assert result.outputs is not None
    step_out = result.outputs["publish_artifact"]
    assert step_out.Result["releaseId"] == "stable:cli"
