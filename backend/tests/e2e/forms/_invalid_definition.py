"""Shared builders and cases for invalid form-prompt and Form Trigger definitions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import pytest
from syntara_api_client.models import WorkflowCreate, WorkflowRead, WorkflowValidateRequest
from syntara_api_client.models.workflow_create_workflow_definition_type_1 import (
    WorkflowCreateWorkflowDefinitionType1,
)
from syntara_api_client.models.workflow_validate_request_workflow_definition import (
    WorkflowValidateRequestWorkflowDefinition,
)

from ._helpers import assert_and_get_response
from ._workflows import (
    dynamic_option_field,
    form_trigger_consumer_workflow,
    producer_prompt_consumer_workflow,
)

if TYPE_CHECKING:
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.types import Response

_DESCRIPTION = "E2E: invalid form definitions"
VALID_TEXT_FIELD: dict[str, Any] = {"type": "text", "value_name": "answer", "label": "Answer", "required": True}
INVALID_DROPDOWN_DEFAULT: dict[str, Any] = {
    "type": "dropdown",
    "value_name": "choice",
    "label": "Choice",
    "required": True,
    "options": {"source": "static", "values": [{"display_label": "Valid", "value": "valid"}]},
    "default": "missing",
}

DefinitionBuilder = Callable[
    [str, list[dict[str, Any]], Mapping[str, Any] | None],
    dict[str, Any],
]


class FormVariant(NamedTuple):
    """The small set of definition differences between the two authored form types."""

    label: str
    element_id: str
    configuration_category: str
    name_prefix: str
    build_definition: DefinitionBuilder
    execution_trigger_node_id: str


def _build_prompt_definition(
    name: str,
    fields: list[dict[str, Any]],
    extra_parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a prompt workflow, then restore raw fields that typed builders may coerce."""
    definition = cast(
        "dict[str, Any]",
        producer_prompt_consumer_workflow(
            name,
            producer_output={},
            form_fields=[VALID_TEXT_FIELD],
        ).to_dict(),
    )
    prompt_node = next(node for node in definition["nodes"] if node["id"] == "prompt")
    parameters = prompt_node["parameters"]
    parameters["form_definition"]["fields"] = deepcopy(fields)
    if extra_parameters:
        parameters.update(deepcopy(dict(extra_parameters)))
    return definition


def _build_trigger_definition(
    name: str,
    fields: list[dict[str, Any]],
    extra_parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a trigger workflow, then restore raw fields and optional raw parameters."""
    definition = cast(
        "dict[str, Any]",
        form_trigger_consumer_workflow(name, form_fields=[VALID_TEXT_FIELD]).to_dict(),
    )
    trigger = definition["triggers"][0]
    parameters = trigger["parameters"]
    parameters["form_definition"]["fields"] = deepcopy(fields)
    if extra_parameters:
        parameters.update(deepcopy(dict(extra_parameters)))
    return definition


PROMPT_VARIANT = FormVariant(
    label="form_prompt",
    element_id="prompt",
    configuration_category="form_prompt_configuration",
    name_prefix="e2e-form-prompt-invalid-definition",
    build_definition=_build_prompt_definition,
    execution_trigger_node_id="trigger",
)
TRIGGER_VARIANT = FormVariant(
    label="form_trigger",
    element_id="form",
    configuration_category="form_trigger_configuration",
    name_prefix="e2e-form-trigger-invalid-definition",
    build_definition=_build_trigger_definition,
    execution_trigger_node_id="form",
)
FORM_VARIANTS = (PROMPT_VARIANT, TRIGGER_VARIANT)


def _workflow_definition(
    variant: FormVariant,
    name: str,
    fields: list[dict[str, Any]],
    extra_parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return variant.build_definition(name, fields, extra_parameters)


def validate_definition(
    syntara_api: SyntaraApiRegistry,
    variant: FormVariant,
    name: str,
    fields: list[dict[str, Any]],
    *,
    extra_parameters: Mapping[str, Any] | None = None,
) -> Response[Any]:
    """Call the stateless validator with a definition for the selected variant."""
    definition = WorkflowValidateRequestWorkflowDefinition.from_dict(
        _workflow_definition(variant, name, fields, extra_parameters)
    )
    return syntara_api.workflows.validate_definition(body=WorkflowValidateRequest(workflow_definition=definition))


def create_workflow(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
    variant: FormVariant,
    *,
    name: str,
    fields: list[dict[str, Any]],
) -> WorkflowRead:
    """Create a draft workflow and register it for fixture cleanup."""
    definition = WorkflowCreateWorkflowDefinitionType1.from_dict(_workflow_definition(variant, name, fields))
    response = syntara_api.workflows.create(
        body=WorkflowCreate(
            name=name,
            description=_DESCRIPTION,
            workflow_definition=definition,
            project_id=first_project_id,
        )
    )
    workflow = assert_and_get_response(response)
    assert response.status_code == HTTPStatus.CREATED
    assert isinstance(workflow, WorkflowRead)
    cleanup_workflows.append(workflow.id)
    return workflow


def element_findings(problem: dict[str, Any], variant: FormVariant) -> list[dict[str, Any]]:
    """Select validation findings for this form element from RFC 9457 details."""
    validation_result = problem["validation_result"]
    return [finding for finding in validation_result["findings"] if finding.get("node_id") == variant.element_id]


# A None expected category means the variant's form configuration category.
_VARIANT_CATEGORY: None = None
_COMMON_CASES: tuple[tuple[str, list[dict[str, Any]], str | None, str, str, int], ...] = (
    (
        "unknown_type",
        [{"type": "not_a_real_type", "value_name": "choice", "label": "Choice"}],
        _VARIANT_CATEGORY,
        "parameters.form_definition.fields.0",
        "",
        1,
    ),
    (
        "invalid_value_name_pattern",
        [{**VALID_TEXT_FIELD, "value_name": "2bad"}],
        "schema_violation",
        "parameters.form_definition.fields.0.value_name",
        "match pattern",
        1,
    ),
    (
        "value_name_too_long",
        [{**VALID_TEXT_FIELD, "value_name": "a" * 65}],
        "schema_violation",
        "parameters.form_definition.fields.0.value_name",
        "",
        1,
    ),
    (
        "empty_label",
        [{**VALID_TEXT_FIELD, "label": ""}],
        "schema_violation",
        "parameters.form_definition.fields.0.label",
        "",
        1,
    ),
    (
        "extra_field_property",
        [{**VALID_TEXT_FIELD, "unexpected": True}],
        "schema_violation",
        "parameters.form_definition.fields.0.unexpected",
        "",
        1,
    ),
    (
        "duplicate_value_names",
        [VALID_TEXT_FIELD, {**VALID_TEXT_FIELD, "label": "Second answer"}],
        _VARIANT_CATEGORY,
        "parameters.form_definition",
        "Duplicate field names are not allowed",
        1,
    ),
    (
        "empty_fields",
        [],
        "schema_violation",
        "parameters.form_definition.fields",
        "",
        1,
    ),
    (
        "date_without_components",
        [
            {
                "type": "date",
                "value_name": "when",
                "label": "When",
                "include_date": False,
                "include_time": False,
                "include_timezone": False,
            }
        ],
        _VARIANT_CATEGORY,
        "parameters.form_definition.fields.0",
        "at least one of include_date, include_time, or include_timezone must be true",
        1,
    ),
    (
        "date_timezone_invalid_combination",
        [
            {
                "type": "date",
                "value_name": "when",
                "label": "When",
                "include_timezone": True,
            }
        ],
        _VARIANT_CATEGORY,
        "parameters.form_definition.fields.0",
        "Select a time when both a date and timezone are included.",
        1,
    ),
    (
        "invalid_calendar_date_default",
        [{"type": "date", "value_name": "when", "label": "When", "default": {"date": "2026-02-30"}}],
        _VARIANT_CATEGORY,
        "parameters.form_definition.fields.0.default.date",
        "Invalid date: '2026-02-30'",
        1,
    ),
    (
        "invalid_timezone_default",
        [
            {
                "type": "date",
                "value_name": "when",
                "label": "When",
                "include_date": False,
                "include_timezone": True,
                "default": {"timezone": "Mars/Olympus"},
            }
        ],
        _VARIANT_CATEGORY,
        "parameters.form_definition.fields.0.default.timezone",
        "Invalid timezone",
        1,
    ),
    (
        "date_default_missing_component",
        [
            {
                "type": "date",
                "value_name": "when",
                "label": "When",
                "include_date": False,
                "include_timezone": True,
                "default": {},
            }
        ],
        _VARIANT_CATEGORY,
        "parameters.form_definition.fields.0",
        "default is missing timezone",
        1,
    ),
    (
        "date_default_extra_component",
        [
            {
                "type": "date",
                "value_name": "when",
                "label": "When",
                "default": {"date": "2026-02-14", "timezone": "UTC"},
            }
        ],
        _VARIANT_CATEGORY,
        "parameters.form_definition.fields.0",
        "default supplies timezone, which this field does not collect",
        1,
    ),
    (
        "empty_static_dropdown_options",
        [
            {
                "type": "dropdown",
                "value_name": "choice",
                "label": "Choice",
                "options": {"source": "static", "values": []},
            }
        ],
        "schema_violation",
        "parameters.form_definition.fields.0.options.values",
        "",
        1,
    ),
    (
        "dropdown_default_not_in_options",
        [INVALID_DROPDOWN_DEFAULT],
        _VARIANT_CATEGORY,
        "parameters.form_definition.fields.0.default",
        "is not in the option list",
        1,
    ),
    (
        "multi_select_default_not_in_options",
        [
            {
                "type": "multi_select",
                "value_name": "choices",
                "label": "Choices",
                "options": {"source": "static", "values": [{"display_label": "Valid", "value": "valid"}]},
                "default": ["missing"],
            }
        ],
        _VARIANT_CATEGORY,
        "parameters.form_definition.fields.0.default",
        "are not in the option list",
        1,
    ),
    (
        "engine_only_dynamic_resolved_options",
        [
            {
                "type": "dropdown",
                "value_name": "choice",
                "label": "Choice",
                "options": {
                    "source": "dynamic_resolved",
                    "values": [{"display_label": "Valid", "value": "valid"}],
                },
            }
        ],
        "schema_violation",
        "parameters.form_definition.fields.0.options",
        "dynamic_resolved",
        2,
    ),
)


def _build_form_field_cases() -> list[Any]:
    cases = []
    for variant in FORM_VARIANTS:
        for case_name, fields, expected_category, field_path, message, expected_count in _COMMON_CASES:
            # The prompt schema/model pair yields two findings; the trigger's static-source schema yields one.
            variant_expected_count = (
                1
                if case_name == "engine_only_dynamic_resolved_options" and variant == TRIGGER_VARIANT
                else expected_count
            )
            cases.append(
                pytest.param(
                    variant,
                    case_name,
                    fields,
                    expected_category,
                    field_path,
                    message,
                    variant_expected_count,
                    id=f"{variant.label}-{case_name}",
                )
            )
    # The trigger schema reports each structural problem with a dynamic source; dynamic_resolved has a separate case.
    cases.append(
        pytest.param(
            TRIGGER_VARIANT,
            "dynamic_options_source",
            [dynamic_option_field("choice", "regions")],
            "schema_violation",
            "parameters.form_definition.fields.0.options",
            "'dynamic' is not one of ['static']",
            5,
            id="form_trigger-dynamic_options_source",
        )
    )
    return cases


FORM_FIELD_CASES = _build_form_field_cases()


PROMPT_ONLY_PARAMETER_CASES = (
    pytest.param("response_window", 30, id="response_window"),
    pytest.param("responder_users", ["alice"], id="responder_users"),
    pytest.param("responder_groups", ["operators"], id="responder_groups"),
    pytest.param("fallback_decision", "submit", id="fallback_decision"),
)
