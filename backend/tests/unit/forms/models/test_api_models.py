"""Tests for form request and response API models."""

import pytest
from pydantic import ValidationError

from syntara.core.models.error import ErrorData
from syntara.forms.models.api_models import FormDataValidationProblem, FormPromptSubmitRequest


class TestFormPromptSubmitRequest:
    """Tests for the user-facing form response request body."""

    def test_accepts_response_data(self) -> None:
        request = FormPromptSubmitRequest(response_data={"name": "Ada"})

        assert request.response_data == {"name": "Ada"}

    def test_requires_response_data(self) -> None:
        with pytest.raises(ValidationError):
            FormPromptSubmitRequest.model_validate({})

    def test_accepts_empty_response_data_for_service_validation(self) -> None:
        request = FormPromptSubmitRequest(response_data={})

        assert request.response_data == {}


class TestFormDataValidationProblemSchema:
    """Tests for the form-specific OpenAPI example."""

    def test_form_problem_has_form_example_and_domain_neutral_base(self) -> None:
        base_schema = ErrorData.model_json_schema()
        form_schema = FormDataValidationProblem.model_json_schema()
        example = form_schema["examples"][0]

        assert "examples" not in base_schema
        assert "LLM" not in str(base_schema)
        assert example["code"] == "FORM_VALIDATION_ERROR"
        assert example["errors"] == [
            {
                "field": "reason",
                "label": "Reason",
                "code": "required",
                "message": "This field is required",
            }
        ]
        assert "LLM" not in str(form_schema)
