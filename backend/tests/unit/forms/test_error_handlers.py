"""Unit tests for form error handlers.

Tests RFC 9457 compliant error responses.
"""

import json
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.constants import FieldLimits
from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.core.models.error import ErrorData
from syntara.forms.error_handlers import (
    form_data_validation_error_handler,
    form_prompt_already_requested_handler,
    form_prompt_already_responded_handler,
    form_prompt_cancelled_handler,
    form_prompt_expired_handler,
    form_prompt_not_found_handler,
)
from syntara.forms.exceptions import (
    FormDataValidationError,
    FormPromptAlreadyRequestedError,
    FormPromptAlreadyRespondedError,
    FormPromptCancelledError,
    FormPromptExpiredError,
    FormPromptNotFoundError,
)
from syntara.forms.models.api_models import FormPromptStatus
from syntara.forms.models.form_errors import FormFieldError


class TestFormPromptNotFoundHandler:
    """Test suite for form_prompt_not_found_handler."""

    def test_handles_form_prompt_not_found_error(self) -> None:
        """Test handling of FormPromptNotFoundError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/forms/12345678-1234-1234-1234-123456789012"

        form_prompt_id = uuid4()
        exc = FormPromptNotFoundError(form_prompt_id)
        response = form_prompt_not_found_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Form Prompt Not Found"
        assert data["detail"] == "The requested form prompt was not found"
        assert data["code"] == "FORM_NOT_FOUND"
        assert data["retryable"] is False


class TestFormPromptAlreadyRespondedHandler:
    """Test suite for form_prompt_already_responded_handler."""

    def test_handles_form_prompt_already_responded_error(self) -> None:
        """Test handling of FormPromptAlreadyRespondedError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/forms/12345678-1234-1234-1234-123456789012"

        form_prompt_id = uuid4()
        exc = FormPromptAlreadyRespondedError(form_prompt_id, FormPromptStatus.SUBMITTED)
        response = form_prompt_already_responded_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_conflict"]
        assert data["title"] == "Form Prompt Already Responded"
        assert data["detail"] == "The form prompt has already been responded to and cannot be modified"
        assert data["code"] == "FORM_ALREADY_RESPONDED"
        assert data["retryable"] is False


class TestFormPromptExpiredHandler:
    """Test suite for form_prompt_expired_handler."""

    def test_handles_form_prompt_expired_error(self) -> None:
        """Test handling of FormPromptExpiredError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/forms/12345678-1234-1234-1234-123456789012"

        form_prompt_id = uuid4()
        exc = FormPromptExpiredError(form_prompt_id, datetime.now(UTC))
        response = form_prompt_expired_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_conflict"]
        assert data["title"] == "Form Prompt Expired"
        assert data["detail"] == "The form prompt has expired and can no longer be responded to"
        assert data["code"] == "FORM_EXPIRED"
        assert data["retryable"] is False


class TestFormPromptCancelledHandler:
    """Test suite for form_prompt_cancelled_handler."""

    def test_handles_form_prompt_cancelled_error(self) -> None:
        """Test handling of FormPromptCancelledError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/forms/12345678-1234-1234-1234-123456789012"

        form_prompt_id = uuid4()
        exc = FormPromptCancelledError(form_prompt_id)
        response = form_prompt_cancelled_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_conflict"]
        assert data["title"] == "Form Prompt Cancelled"
        assert data["detail"] == "The form prompt has been cancelled and can no longer be responded to"
        assert data["code"] == "FORM_CANCELLED"
        assert data["retryable"] is False


class TestFormPromptAlreadyRequestedHandler:
    """Test suite for form_prompt_already_requested_handler."""

    def test_handles_form_prompt_already_requested_error(self) -> None:
        """Test handling of FormPromptAlreadyRequestedError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/forms"

        execution_id = uuid4()
        prompt_node_id = "form_task_1"
        exc = FormPromptAlreadyRequestedError(execution_id, prompt_node_id)
        response = form_prompt_already_requested_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_conflict"]
        assert data["title"] == "Form Prompt Already Requested"
        assert "A form prompt already exists for this execution and prompt node" in data["detail"]
        assert prompt_node_id in data["detail"]
        assert data["code"] == "FORM_ALREADY_REQUESTED"
        assert data["retryable"] is False


class TestFormDataValidationErrorHandler:
    """Test the RFC 9457 response for invalid form submissions."""

    def test_response_uses_standard_problem_details_with_concatenated_errors(self) -> None:
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/form_prompts/123/submit"
        exc = FormDataValidationError(
            errors=[
                FormFieldError(
                    field="reason",
                    label="Reason",
                    code="required",
                    message="This field is required",
                )
            ]
        )

        response = form_data_validation_error_handler(request, exc)

        assert response.status_code == 422
        assert response.media_type == "application/problem+json"
        problem = ErrorData.model_validate(json.loads(bytes(response.body)))
        assert problem.type == PROBLEM_TYPES["validation_error"]
        assert problem.title == "Form Validation Error"
        assert problem.detail == "Form validation failed: reason: This field is required"
        assert problem.code == "FORM_VALIDATION_ERROR"
        assert problem.retryable is False
        assert problem.instance == str(request.url)
        assert "errors" not in json.loads(bytes(response.body))

    def test_truncates_concatenated_detail(self) -> None:
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/form_prompts/123/submit"
        errors = [
            FormFieldError(
                field=f"field_{index}",
                label=f"Field {index}",
                code="invalid",
                message="x" * 100,
            )
            for index in range(100)
        ]

        response = form_data_validation_error_handler(request, FormDataValidationError(errors=errors))
        data = json.loads(bytes(response.body))

        assert response.status_code == 422
        assert len(data["detail"]) == FieldLimits.DESCRIPTION_MAX_LENGTH
        assert data["detail"].endswith("...")
        assert "errors" not in data
