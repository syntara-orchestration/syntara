"""Workflow definitions containing target UUIDs must be safe for JSON storage."""

import json
from uuid import uuid4

from syntara.workflows.models.workflow_definition import WorkflowDefinition
from syntara.workflows.router import _definition_to_dict


def test_execution_target_profile_is_json_serializable() -> None:
    target_id = uuid4()
    definition = WorkflowDefinition.model_validate(
        {
            "schema_version": "2.0.0",
            "name": "target-profile",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "script",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": "echo hello",
                        "execution_profile": {"type": "execution_target", "execution_target_id": str(target_id)},
                    },
                }
            ],
            "edges": [{"from": "trigger", "to": "script"}],
        }
    )

    stored = json.loads(json.dumps(_definition_to_dict(definition)))

    assert stored["nodes"][0]["parameters"]["execution_profile"] == {
        "type": "execution_target",
        "execution_target_id": str(target_id),
    }
