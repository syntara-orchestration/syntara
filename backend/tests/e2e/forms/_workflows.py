"""Workflow builders shared by the form-prompt E2E modules."""

import json
from collections.abc import Mapping
from typing import Any

from syntara_api_client.models import WorkflowDefinition

DEFAULT_CONSUMER_CODE = 'print("submitted path executed")'


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
    consumer_code: str = DEFAULT_CONSUMER_CODE,
    consumer_environment: Mapping[str, str] | None = None,
    continue_on_failure: bool = False,
    response_window: int = 600,
    responder_users: list[str] | None = None,
    responder_groups: list[str] | None = None,
) -> WorkflowDefinition:
    """Build a trigger, producer, form prompt, consumer, and optional fallback chain.

    Optional responder lists restrict which users or group members may submit
    the form prompt. ``consumer_code`` can inspect the prompt response.
    """
    payload = json.dumps(producer_output)
    consumer_parameters: dict[str, Any] = {"language": "python", "code": consumer_code}
    if consumer_environment is not None:
        consumer_parameters["environment"] = dict(consumer_environment)
    prompt_parameters: dict[str, Any] = {
        "message": "Choose an environment",
        "form_definition": {"fields": form_fields},
        "response_window": response_window,
    }
    if responder_users:
        prompt_parameters["responder_users"] = responder_users
    if responder_groups:
        prompt_parameters["responder_groups"] = responder_groups

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
            "parameters": prompt_parameters,
            "settings": {"continue_on_failure": continue_on_failure},
        },
        {
            "id": "consumer",
            "name": "Consumer Node",
            "type": "script",
            "parameters": consumer_parameters,
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
        nodes.append(
            {
                "id": "fallback_consumer",
                "name": "Fallback Consumer Node",
                "type": "script",
                "parameters": {"language": "bash", "code": 'echo "after fallback path executed"'},
            }
        )
        edges.append({"from": "prompt", "to": "fallback_handler", "from_port": "fallback"})
        edges.append({"from": "fallback_handler", "to": "fallback_consumer"})

    return WorkflowDefinition.from_dict(
        {
            "name": name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": nodes,
            "edges": edges,
        }
    )


APPROVAL_REASON_FIELD: dict[str, Any] = {
    "type": "text",
    "value_name": "reason",
    "label": "Reason",
    "required": True,
}


ENVIRONMENT_RECORDS = [
    {"display_label": "Development", "value": "dev"},
    {"display_label": "Staging", "value": "staging"},
    {"display_label": "Production", "value": "prod"},
]
