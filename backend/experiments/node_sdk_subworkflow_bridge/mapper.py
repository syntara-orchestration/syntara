"""Map node-sdk Control/Trigger documents onto AO sub-workflow shapes.

The three known contract gaps are explicit injection points on
``BridgeInjection``. This module never starts Temporal children or calls
production activities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from syntara.workflows.workflow_engine.models.workflow_definition import (
    SubWorkflowExecutorParameters,
)


@dataclass(frozen=True, slots=True)
class BridgeInjection:
    """Values AO requires that SDK Control documents do not carry."""

    workflow_id: str
    trigger_node_id: str
    input_mapping: dict[str, Any] | None = None


class BridgeMappingError(ValueError):
    """Raised when a Control/Trigger document cannot be mapped to AO V1."""


def _require_control(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("kind") != "Control":
        msg = f"expected kind Control, got {document.get('kind')!r}"
        raise BridgeMappingError(msg)
    spec = document.get("spec")
    if not isinstance(spec, dict):
        msg = "Control.spec must be an object"
        raise BridgeMappingError(msg)
    invocation = spec.get("invocation")
    if not isinstance(invocation, dict) or invocation.get("kind") != "workflow-invocation":
        msg = "Control.spec.invocation.kind must be workflow-invocation"
        raise BridgeMappingError(msg)
    if "workflow" not in invocation:
        msg = "Control.spec.invocation.workflow is required"
        raise BridgeMappingError(msg)
    return spec


def map_control_to_ao_parameters(
    control: dict[str, Any],
    injection: BridgeInjection,
) -> SubWorkflowExecutorParameters:
    """Build AO ``SubWorkflowExecutorParameters`` from a Control document.

    ``spec.invocation.workflow`` (qualified identifier) cannot populate
    ``workflow_id``; callers must inject the UUID via ``BridgeInjection``.
    """
    spec = _require_control(control)
    invocation = spec["invocation"]
    qualified = invocation["workflow"]
    if not isinstance(qualified, str) or "." not in qualified:
        msg = f"expected qualifiedIdentifier workflow, got {qualified!r}"
        raise BridgeMappingError(msg)

    try:
        UUID(injection.workflow_id)
    except ValueError as exc:
        msg = f"injection.workflow_id must be a UUID, got {injection.workflow_id!r}"
        raise BridgeMappingError(msg) from exc

    if not injection.trigger_node_id:
        msg = "injection.trigger_node_id is required"
        raise BridgeMappingError(msg)

    mapping = injection.input_mapping
    if mapping is None:
        mapping = {}

    return SubWorkflowExecutorParameters(
        workflow_id=injection.workflow_id,
        trigger_node_id=injection.trigger_node_id,
        input_mapping=mapping,
    )


def map_trigger_configuration_to_input_schema(
    trigger: dict[str, Any],
) -> dict[str, Any]:
    """Extract AO ``parameters.input_schema`` from a Trigger's configuration."""
    if trigger.get("kind") != "Trigger":
        msg = f"expected kind Trigger, got {trigger.get('kind')!r}"
        raise BridgeMappingError(msg)
    spec = trigger.get("spec")
    if not isinstance(spec, dict):
        msg = "Trigger.spec must be an object"
        raise BridgeMappingError(msg)
    if spec.get("driver") != "subworkflow.v1":
        msg = f"expected driver subworkflow.v1, got {spec.get('driver')!r}"
        raise BridgeMappingError(msg)
    configuration = spec.get("configuration")
    if not isinstance(configuration, dict) or configuration.get("kind") != "inline":
        msg = "Trigger.spec.configuration must be inline"
        raise BridgeMappingError(msg)
    value = configuration.get("value")
    if not isinstance(value, dict):
        msg = "Trigger.spec.configuration.value must be an object"
        raise BridgeMappingError(msg)
    return value


def wrap_sdk_output_as_ao_result(
    business_result: dict[str, Any],
    *,
    child_execution_id: str,
    child_workflow_id: str,
    child_workflow_name: str,
    child_workflow_version: int,
    child_status: str = "completed",
    terminal_step_id: str = "terminal",
) -> dict[str, Any]:
    """Wrap an SDK business result into an AO SubWorkflowOutput.Result-shaped dict."""
    return {
        "child_execution_id": child_execution_id,
        "child_workflow_id": child_workflow_id,
        "child_workflow_name": child_workflow_name,
        "child_workflow_version": child_workflow_version,
        "child_status": child_status,
        "outputs": {
            terminal_step_id: {
                "Result": business_result,
                "StatusCode": 0,
                "StatusMessage": "Completed",
                "ErrorMessage": None,
            }
        },
    }


def qualified_workflow_from_control(control: dict[str, Any]) -> str:
    """Return the SDK qualified workflow name for logging / catalog lookup."""
    spec = _require_control(control)
    workflow = spec["invocation"]["workflow"]
    if not isinstance(workflow, str):
        msg = f"expected string workflow identifier, got {type(workflow).__name__}"
        raise BridgeMappingError(msg)
    return workflow
