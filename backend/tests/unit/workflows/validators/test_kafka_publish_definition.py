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
        {"integration_id": "11111111-1111-4111-8111-111111111111", "topic": "outcomes", "payload": None, **patch}
    )
    with pytest.raises(SafeValueError):
        WorkflowValidator().validate_workflow_definition(definition)
