"""Schema/model conformance tests for the typed 409 confirmation problems.

Two independent checks are kept distinct:

* Model conformance -- the backend Pydantic models accept/reject bodies (``model_validate``).
* OpenAPI conformance -- the *published* OpenAPI schema (loaded from the YAML and validated with
  ``jsonschema``) accepts/rejects the same bodies, independent of the Pydantic models.

A consistency test pins the two representations together so they cannot silently drift.

Each confirmation model is the *single* model for every 409 the endpoint returns: ``code`` is
inherited from ``ErrorData`` (any 409 code validates) and the count is optional, so generic 409
bodies (active executions, version conflict) validate against the same schema. Only an
out-of-range count (< 1) is rejected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from syntara.workflows.error_handlers import (
    WorkflowPublishTriggerRemovalConfirmationProblem,
    WorkflowReferencedConfirmationProblem,
)

_BACKEND = Path(__file__).parents[3]
_SUBSPEC = _BACKEND / "src/syntara/schemas/workflows/v2/openapi.yaml"
_SHARED = _BACKEND / "src/syntara/schemas/base/shared-resources.openapi.yaml"

_REF_CODE = "WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED"
_PUB_CODE = "WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED"


def _published_schema(schema_name: str) -> dict[str, Any]:
    """Load a specialized problem schema from the YAML.

    The published schema is a self-contained flat object: the Pydantic model subclasses
    ``ErrorData`` and Pydantic inlines the inherited fields, so the schema carries them directly
    (no ``allOf``/``$ref``) and can be validated with ``jsonschema`` as-is.
    """
    subspec = yaml.safe_load(_SUBSPEC.read_text())
    return dict(subspec["components"]["schemas"][schema_name])


def _base_body(code: str) -> dict[str, Any]:
    return {
        "type": "https://api.example.com/errors/conflict",
        "title": "Confirmation Required",
        "detail": "x",
        "code": code,
        "retryable": False,
    }


class TestOpenAPISchemaConformance:
    """Validate bodies against the PUBLISHED OpenAPI schema (jsonschema), not the Pydantic model."""

    def test_valid_referenced_body_conforms(self) -> None:
        schema = _published_schema("WorkflowReferencedConfirmationProblem")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate({**_base_body(_REF_CODE), "referencing_count": 2})

    def test_generic_referenced_body_conforms(self) -> None:
        """A generic 409 (any code, no count) validates against the single model (count is optional)."""
        schema = _published_schema("WorkflowReferencedConfirmationProblem")
        Draft202012Validator(schema).validate(_base_body("ACTIVE_EXECUTIONS_BLOCK_DELETION"))

    @pytest.mark.parametrize(
        "body",
        [
            {**_base_body(_REF_CODE), "referencing_count": 0},
            {**_base_body(_REF_CODE), "referencing_count": -1},
        ],
    )
    def test_malformed_referenced_body_rejected(self, body: dict[str, Any]) -> None:
        """Only an out-of-range count is rejected now; code is generic and the count is optional."""
        schema = _published_schema("WorkflowReferencedConfirmationProblem")
        with pytest.raises(jsonschema.ValidationError):
            Draft202012Validator(schema).validate(body)

    def test_valid_publish_body_conforms(self) -> None:
        schema = _published_schema("WorkflowPublishTriggerRemovalConfirmationProblem")
        Draft202012Validator(schema).validate({**_base_body(_PUB_CODE), "affected_count": 1})

    def test_generic_publish_body_conforms(self) -> None:
        """A generic 409 (any code, no count) validates against the single model (count is optional)."""
        schema = _published_schema("WorkflowPublishTriggerRemovalConfirmationProblem")
        Draft202012Validator(schema).validate(_base_body("WORKFLOW_VERSION_CONFLICT"))

    @pytest.mark.parametrize(
        "body",
        [
            {**_base_body(_PUB_CODE), "affected_count": 0},
            {**_base_body(_PUB_CODE), "affected_count": -3},
        ],
    )
    def test_malformed_publish_body_rejected(self, body: dict[str, Any]) -> None:
        schema = _published_schema("WorkflowPublishTriggerRemovalConfirmationProblem")
        with pytest.raises(jsonschema.ValidationError):
            Draft202012Validator(schema).validate(body)

    def test_generic_conflict_conforms_to_both_shapes(self) -> None:
        """A generic 409 body (no count) validates against both ErrorData and the single 409 model."""
        shared = yaml.safe_load(_SHARED.read_text())
        error_data = shared["components"]["schemas"]["ErrorData"]
        generic = _base_body("ACTIVE_EXECUTIONS_BLOCK_DELETION")
        Draft202012Validator(error_data).validate(generic)
        Draft202012Validator(_published_schema("WorkflowReferencedConfirmationProblem")).validate(generic)


class TestModelConformance:
    """Pydantic model validation (distinct from the OpenAPI conformance above)."""

    @pytest.mark.parametrize(
        "body",
        [
            {**_base_body(_REF_CODE), "referencing_count": 0},
            {**_base_body(_REF_CODE), "referencing_count": -1},
        ],
    )
    def test_referenced_model_rejects_out_of_range_count(self, body: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            WorkflowReferencedConfirmationProblem.model_validate(body)

    def test_referenced_model_accepts_generic_body(self) -> None:
        """A generic 409 body (any code, no count) is accepted by the single model."""
        WorkflowReferencedConfirmationProblem.model_validate(_base_body("ACTIVE_EXECUTIONS_BLOCK_DELETION"))

    @pytest.mark.parametrize(
        "body",
        [
            {**_base_body(_PUB_CODE), "affected_count": 0},
            {**_base_body(_PUB_CODE), "affected_count": -3},
        ],
    )
    def test_publish_model_rejects_out_of_range_count(self, body: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            WorkflowPublishTriggerRemovalConfirmationProblem.model_validate(body)

    def test_publish_model_accepts_generic_body(self) -> None:
        WorkflowPublishTriggerRemovalConfirmationProblem.model_validate(_base_body("WORKFLOW_VERSION_CONFLICT"))


class TestModelOpenAPIConsistency:
    """Pin the Pydantic models and the published OpenAPI schemas together so they cannot drift."""

    @staticmethod
    def _int_branch_minimum(prop: dict[str, Any]) -> float | None:
        for branch in prop.get("anyOf", []):
            if branch.get("type") == "integer":
                minimum = branch.get("minimum")
                return minimum if isinstance(minimum, (int, float)) else None
        return None

    def test_referenced_constraints_match(self) -> None:
        subspec = yaml.safe_load(_SUBSPEC.read_text())
        schema = subspec["components"]["schemas"]["WorkflowReferencedConfirmationProblem"]
        # code is inherited from ErrorData (generic string), not a fixed literal/const.
        assert "const" not in schema["properties"]["code"]
        assert schema["properties"]["code"]["type"] == "string"
        # the count is optional (not required) and nullable, with the >=1 bound on the int branch.
        assert "referencing_count" not in schema.get("required", [])
        assert self._int_branch_minimum(schema["properties"]["referencing_count"]) == 1
        assert not WorkflowReferencedConfirmationProblem.model_fields["referencing_count"].is_required()

    def test_publish_constraints_match(self) -> None:
        subspec = yaml.safe_load(_SUBSPEC.read_text())
        schema = subspec["components"]["schemas"]["WorkflowPublishTriggerRemovalConfirmationProblem"]
        assert "const" not in schema["properties"]["code"]
        assert schema["properties"]["code"]["type"] == "string"
        assert "affected_count" not in schema.get("required", [])
        assert self._int_branch_minimum(schema["properties"]["affected_count"]) == 1
        assert not WorkflowPublishTriggerRemovalConfirmationProblem.model_fields["affected_count"].is_required()
