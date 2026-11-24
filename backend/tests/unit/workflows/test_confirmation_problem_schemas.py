"""Schema/model conformance tests for the typed 409 confirmation problems.

Two independent checks are kept distinct:

* Model conformance -- the backend Pydantic models accept/reject bodies (``model_validate``).
* OpenAPI conformance -- the *published* OpenAPI schema (loaded from the YAML and validated with
  ``jsonschema``) accepts/rejects the same bodies, independent of the Pydantic models.

A consistency test pins the two representations together so they cannot silently drift.
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
    """Load a specialized problem schema from the YAML, inlining the ErrorData allOf ``$ref``."""
    subspec = yaml.safe_load(_SUBSPEC.read_text())
    shared = yaml.safe_load(_SHARED.read_text())
    error_data = shared["components"]["schemas"]["ErrorData"]
    schema = dict(subspec["components"]["schemas"][schema_name])
    schema["allOf"] = [error_data if "$ref" in part else part for part in schema["allOf"]]
    return schema


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

    @pytest.mark.parametrize(
        "body",
        [
            _base_body(_REF_CODE),
            {**_base_body(_REF_CODE), "referencing_count": 0},
            {**_base_body(_REF_CODE), "referencing_count": -1},
            {**_base_body("SOMETHING_ELSE"), "referencing_count": 2},
            {**_base_body(_REF_CODE), "affected_count": 2},
        ],
    )
    def test_malformed_referenced_body_rejected(self, body: dict[str, Any]) -> None:
        schema = _published_schema("WorkflowReferencedConfirmationProblem")
        with pytest.raises(jsonschema.ValidationError):
            Draft202012Validator(schema).validate(body)

    def test_valid_publish_body_conforms(self) -> None:
        schema = _published_schema("WorkflowPublishTriggerRemovalConfirmationProblem")
        Draft202012Validator(schema).validate({**_base_body(_PUB_CODE), "affected_count": 1})

    @pytest.mark.parametrize(
        "body",
        [
            _base_body(_PUB_CODE),
            {**_base_body(_PUB_CODE), "affected_count": 0},
            {**_base_body(_PUB_CODE), "affected_count": -3},
            {**_base_body("SOMETHING_ELSE"), "affected_count": 1},
        ],
    )
    def test_malformed_publish_body_rejected(self, body: dict[str, Any]) -> None:
        schema = _published_schema("WorkflowPublishTriggerRemovalConfirmationProblem")
        with pytest.raises(jsonschema.ValidationError):
            Draft202012Validator(schema).validate(body)

    def test_generic_conflict_matches_errordata_not_specialized(self) -> None:
        """An unrelated 409 body (no count) conforms to the generic ErrorData branch, not the specialized schema."""
        shared = yaml.safe_load(_SHARED.read_text())
        error_data = shared["components"]["schemas"]["ErrorData"]
        generic = _base_body("ACTIVE_EXECUTIONS_BLOCK_DELETION")
        Draft202012Validator(error_data).validate(generic)
        with pytest.raises(jsonschema.ValidationError):
            Draft202012Validator(_published_schema("WorkflowReferencedConfirmationProblem")).validate(generic)


class TestModelConformance:
    """Negative Pydantic model validation (distinct from the OpenAPI conformance above)."""

    @pytest.mark.parametrize(
        "body",
        [
            _base_body(_REF_CODE),
            {**_base_body(_REF_CODE), "referencing_count": 0},
            {**_base_body(_REF_CODE), "referencing_count": -1},
            {**_base_body("WRONG_CODE"), "referencing_count": 2},
        ],
    )
    def test_referenced_model_rejects_malformed(self, body: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            WorkflowReferencedConfirmationProblem.model_validate(body)

    @pytest.mark.parametrize(
        "body",
        [
            _base_body(_PUB_CODE),
            {**_base_body(_PUB_CODE), "affected_count": 0},
            {**_base_body("WRONG_CODE"), "affected_count": 1},
        ],
    )
    def test_publish_model_rejects_malformed(self, body: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            WorkflowPublishTriggerRemovalConfirmationProblem.model_validate(body)


class TestModelOpenAPIConsistency:
    """Pin the Pydantic models and the published OpenAPI schemas together so they cannot drift."""

    def test_referenced_constraints_match(self) -> None:
        subspec = yaml.safe_load(_SUBSPEC.read_text())
        ext = next(
            p
            for p in subspec["components"]["schemas"]["WorkflowReferencedConfirmationProblem"]["allOf"]
            if "$ref" not in p
        )
        assert ext["properties"]["code"]["enum"] == [_REF_CODE]
        assert "referencing_count" in ext["required"]
        assert ext["properties"]["referencing_count"]["minimum"] == 1
        assert WorkflowReferencedConfirmationProblem.model_fields["referencing_count"].is_required()

    def test_publish_constraints_match(self) -> None:
        subspec = yaml.safe_load(_SUBSPEC.read_text())
        ext = next(
            p
            for p in subspec["components"]["schemas"]["WorkflowPublishTriggerRemovalConfirmationProblem"]["allOf"]
            if "$ref" not in p
        )
        assert ext["properties"]["code"]["enum"] == [_PUB_CODE]
        assert "affected_count" in ext["required"]
        assert ext["properties"]["affected_count"]["minimum"] == 1
        assert WorkflowPublishTriggerRemovalConfirmationProblem.model_fields["affected_count"].is_required()
