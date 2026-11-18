"""The API validator accepts Publish without weakening other node schemas."""

from typing import Any

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.workflows.models.workflow_definition import WorkflowDefinition
from syntara.workflows.validators.workflow_definition import WorkflowValidator


def _definition(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "publish-outcome",
        "triggers": [{"id": "manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "publish",
                "type": "kafka_publish",
                "parameters": parameters,
                "settings": {"retry_policy": {"max_retries": 0}},
            }
        ],
        "edges": [{"from": "manual", "to": "publish"}],
    }


def test_api_and_runtime_schemas_accept_json_null_and_header_templates() -> None:
    definition = _definition(
        {
            "integration_id": "11111111-1111-4111-8111-111111111111",
            "credential_id": "22222222-2222-4222-8222-222222222222",
            "topic": "outcomes",
            "payload": None,
            "headers": "${trigger.headers}",
        }
    )
    WorkflowValidator().validate_workflow_definition(definition)
    model = WorkflowDefinition.model_validate(definition)
    assert model.nodes[0].type == "kafka_publish"


def test_api_schema_resolves_encoded_key_and_header_definitions() -> None:
    definition = _definition(
        {
            "integration_id": "11111111-1111-4111-8111-111111111111",
            "credential_id": "22222222-2222-4222-8222-222222222222",
            "topic": "outcomes",
            "payload": [True, None],
            "key": {"encoding": "base64", "value": "AAEC"},
            "headers": [{"name": "x", "value": {"encoding": "utf-8", "value": "value"}}],
        }
    )
    WorkflowValidator().validate_workflow_definition(definition)
    WorkflowDefinition.model_validate(definition)


@pytest.mark.parametrize(
    "patch",
    [
        {"topic": "${trigger.topic}"},
        {"integration_id": "${trigger.integration}"},
        {"credential_id": "${trigger.credential}"},
        {"acks": 1},
        {"partition": 0},
    ],
)
def test_api_schema_rejects_dynamic_destinations_and_producer_overrides(patch: dict[str, Any]) -> None:
    definition = _definition(
        {
            "integration_id": "11111111-1111-4111-8111-111111111111",
            "credential_id": "22222222-2222-4222-8222-222222222222",
            "topic": "outcomes",
            "payload": None,
            **patch,
        }
    )
    with pytest.raises(SafeValueError):
        WorkflowValidator().validate_workflow_definition(definition)


@pytest.mark.parametrize("omit", [True, False])
def test_api_schema_requires_non_null_runtime_credential(*, omit: bool) -> None:
    parameters = {"integration_id": "11111111-1111-4111-8111-111111111111", "topic": "outcomes", "payload": None}
    if not omit:
        parameters["credential_id"] = None
    with pytest.raises(SafeValueError):
        WorkflowValidator().validate_workflow_definition(_definition(parameters))


@pytest.mark.parametrize("parameters", [{}, {"integration_id": "", "credential_id": None, "topic": ""}])
def test_incomplete_publish_is_reported_as_safe_workflow_findings(parameters: dict[str, Any]) -> None:
    definition = _definition(parameters)
    definition["nodes"][0]["metadata"] = {"__kafkaPublishPayloadDraft": '{"sensitive":'}
    result = WorkflowValidator().collect_findings(definition)
    assert not result.is_valid
    fields = {finding.field_path for finding in result.findings if finding.node_id == "publish"}
    assert {"parameters.integration_id", "parameters.credential_id", "parameters.topic", "parameters.payload"} <= fields
    assert "sensitive" not in result.model_dump_json()
    with pytest.raises(SafeValueError):
        WorkflowValidator().validate_workflow_definition(definition)


@pytest.mark.parametrize(
    ("field", "value"),
    [("key", {"encoding": "base64", "value": "invalid"}), ("headers", [{"name": "x", "value": None}] * 129)],
)
def test_invalid_message_bytes_and_header_limits_gate_execution(field: str, value: object) -> None:
    definition = _definition(
        {
            "integration_id": "11111111-1111-4111-8111-111111111111",
            "credential_id": "22222222-2222-4222-8222-222222222222",
            "topic": "outcomes",
            "payload": None,
            field: value,
        }
    )
    result = WorkflowValidator().collect_findings(definition)
    assert not result.is_valid
    assert any(
        f.node_id == "publish" and (f.field_path or "").startswith(f"parameters.{field}") for f in result.findings
    )
