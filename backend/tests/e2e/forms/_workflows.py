"""Workflow builders shared by the form-prompt E2E modules."""

import json
from collections.abc import Mapping
from typing import Any

from syntara_api_client.models import WorkflowDefinition


def dynamic_option_field(
    value_name: str,
    expression: str,
    *,
    field_type: str = "dropdown",
    required: bool = True,
) -> dict[str, Any]:
    """Build a dropdown or multi-select whose options come from an expression."""
    return {
        "type": field_type,
        "value_name": value_name,
        "label": value_name.replace("_", " ").title(),
        "required": required,
        "options": {
            "source": "dynamic",
            "expression": expression,
            "label_key": "display_label",
            "value_key": "value",
        },
    }


def producer_prompt_consumer_workflow(
    name: str,
    *,
    producer_output: Mapping[str, object],
    form_fields: list[dict[str, Any]],
    continue_on_failure: bool = False,
) -> WorkflowDefinition:
    """Build a trigger, Python producer, form prompt, and downstream consumer."""
    payload = json.dumps(producer_output)
    nodes: list[dict[str, Any]] = [
        {
            "id": "producer",
            "name": "Producer Node",
            "type": "script",
            "parameters": {"language": "python", "code": f"print({payload!r})"},
        },
        {
            "id": "prompt",
            "name": "Collect Input",
            "type": "form_prompt",
            "parameters": {
                "message": "Choose an environment",
                "form_definition": {"fields": form_fields},
                "response_window": 600,
            },
            "settings": {"continue_on_failure": continue_on_failure},
        },
        {
            "id": "consumer",
            "name": "Consumer Node",
            "type": "script",
            "parameters": {"language": "bash", "code": 'echo "submitted path executed"'},
        },
    ]
    edges: list[dict[str, Any]] = [
        {"from": "trigger", "to": "producer"},
        {"from": "producer", "to": "prompt"},
        {"from": "prompt", "to": "consumer", "from_port": "submitted"},
    ]

    if continue_on_failure:
        nodes.append(
            {
                "id": "fallback_handler",
                "name": "Fallback Handler",
                "type": "script",
                "parameters": {"language": "bash", "code": 'echo "fallback path executed"'},
            }
        )
        edges.append({"from": "prompt", "to": "fallback_handler", "from_port": "fallback"})

    return WorkflowDefinition.from_dict(
        {
            "name": name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": nodes,
            "edges": edges,
        }
    )


ENVIRONMENT_RECORDS = [
    {"display_label": "Development", "value": "dev"},
    {"display_label": "Staging", "value": "staging"},
    {"display_label": "Production", "value": "prod"},
]
