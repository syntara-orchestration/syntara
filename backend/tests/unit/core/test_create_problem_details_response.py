"""Unit tests for create_problem_details_response utility function."""

import json

import pytest
from fastapi.responses import JSONResponse
from pydantic import Field as PydanticField

from syntara.core.error_handlers import (
    PROBLEM_TYPES,
    create_problem_details_response,
    create_problem_details_response_from_model,
    truncate_problem_instance,
)
from syntara.core.models.error import ErrorData


class TestCreateProblemDetailsResponse:
    """Test suite for create_problem_details_response utility."""

    def test_create_basic_response(self) -> None:
        """Test creating a basic problem details response."""
        response = create_problem_details_response(
            status_code=404,
            problem_type=PROBLEM_TYPES["resource_not_found"],
            title="Not Found",
            detail="The resource was not found",
            code="NOT_FOUND",
        )

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        # Parse the response content
        data = json.loads(bytes(response.body).decode())

        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Not Found"
        assert data["detail"] == "The resource was not found"
        assert data["code"] == "NOT_FOUND"
        assert data["retryable"] is False
        assert "instance" not in data  # instance=None is excluded

    def test_create_response_with_all_fields(self) -> None:
        """Test creating a response with all optional fields."""
        response = create_problem_details_response(
            status_code=500,
            problem_type=PROBLEM_TYPES["internal_error"],
            title="Internal Server Error",
            detail="An unexpected error occurred",
            code="INTERNAL_ERROR",
            retryable=True,
            instance="https://api.example.com/users/123",
        )

        assert response.status_code == 500

        data = json.loads(bytes(response.body).decode())

        assert data["retryable"] is True
        assert data["instance"] == "https://api.example.com/users/123"

    def test_response_content_structure(self) -> None:
        """Test that response content follows RFC 9457 structure."""
        response = create_problem_details_response(
            status_code=400,
            problem_type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="Invalid input provided",
            code="VALIDATION_ERROR",
        )

        data = json.loads(bytes(response.body).decode())

        # Check all required RFC 9457 fields are present
        required_fields = {"type", "title", "detail", "code", "retryable"}
        assert all(field in data for field in required_fields)

        # Check field types
        assert isinstance(data["type"], str)
        assert isinstance(data["title"], str)
        assert isinstance(data["detail"], str)
        assert isinstance(data["code"], str)
        assert isinstance(data["retryable"], bool)

    def test_retryable_defaults_to_false(self) -> None:
        """Test that retryable defaults to False when not specified."""
        response = create_problem_details_response(
            status_code=400,
            problem_type=PROBLEM_TYPES["validation_error"],
            title="Bad Request",
            detail="Invalid data",
            code="BAD_REQUEST",
        )

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False

    def test_instance_can_be_none(self) -> None:
        """Test that instance field can be None."""
        response = create_problem_details_response(
            status_code=404,
            problem_type=PROBLEM_TYPES["resource_not_found"],
            title="Not Found",
            detail="Resource not found",
            code="NOT_FOUND",
            instance=None,
        )

        data = json.loads(bytes(response.body).decode())
        assert "instance" not in data  # instance=None is excluded by exclude_none=True

    @pytest.mark.parametrize(
        ("status_code", "expected_code"),
        [
            (200, 200),
            (400, 400),
            (404, 404),
            (500, 500),
            (503, 503),
        ],
    )
    def test_status_code_preservation(self, status_code: int, expected_code: int) -> None:
        """Test that status codes are preserved correctly."""
        response = create_problem_details_response(
            status_code=status_code,
            problem_type=PROBLEM_TYPES["internal_error"],
            title="Error",
            detail="Error detail",
            code="ERROR_CODE",
        )
        assert response.status_code == expected_code

    def test_media_type_is_correct(self) -> None:
        """Test that media type is set to application/problem+json."""
        response = create_problem_details_response(
            status_code=400,
            problem_type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="Invalid input",
            code="VALIDATION_ERROR",
        )
        assert response.media_type == "application/problem+json"

    def test_detail_truncated_when_exceeding_max_length(self) -> None:
        """Test that detail is truncated with ellipsis when it exceeds max length."""
        long_detail = "x" * 3000

        response = create_problem_details_response(
            status_code=422,
            problem_type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=long_detail,
            code="VALIDATION_ERROR",
        )

        data = json.loads(bytes(response.body).decode())
        assert len(data["detail"]) == 2000
        assert data["detail"].endswith("...")

    def test_detail_preserved_when_within_max_length(self) -> None:
        """Test that detail is not truncated when within limits."""
        detail = "Short error message"

        response = create_problem_details_response(
            status_code=422,
            problem_type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=detail,
            code="VALIDATION_ERROR",
        )

        data = json.loads(bytes(response.body).decode())
        assert data["detail"] == detail

    def test_detail_at_exact_max_length_is_not_truncated(self) -> None:
        """Test that detail at exactly max length is preserved."""
        detail = "x" * 2000

        response = create_problem_details_response(
            status_code=422,
            problem_type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=detail,
            code="VALIDATION_ERROR",
        )

        data = json.loads(bytes(response.body).decode())
        assert data["detail"] == detail
        assert len(data["detail"]) == 2000


class _CountProblem(ErrorData):
    """Test-only ErrorData extension carrying a required positive count (mirrors the confirmation problems)."""

    extra_count: int = PydanticField(ge=1)


class TestCreateProblemDetailsResponseFromModel:
    """Tests for the shared model-based problem serializer and delegation."""

    def test_serializes_subclass_extension_field(self) -> None:
        problem = _CountProblem(
            type=PROBLEM_TYPES["resource_conflict"],
            title="Conflict",
            detail="x",
            code="SOME_CONFIRMATION_REQUIRED",
            retryable=False,
            instance="/api/v1/x",
            extra_count=3,
        )
        resp = create_problem_details_response_from_model(problem, status_code=409)
        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 409
        assert resp.media_type == "application/problem+json"
        data = json.loads(bytes(resp.body).decode())
        assert data["extra_count"] == 3
        assert data["code"] == "SOME_CONFIRMATION_REQUIRED"
        assert data["retryable"] is False

    def test_public_helper_delegates_identically(self) -> None:
        """create_problem_details_response must emit the same wire bytes as from_model for an equivalent model."""
        via_public = create_problem_details_response(
            status_code=409,
            problem_type=PROBLEM_TYPES["resource_conflict"],
            title="Conflict",
            detail="boom",
            code="CONFLICT",
            retryable=True,
            instance="/api/v1/thing",
        )
        via_model = create_problem_details_response_from_model(
            ErrorData(
                type=PROBLEM_TYPES["resource_conflict"],
                title="Conflict",
                detail="boom",
                code="CONFLICT",
                retryable=True,
                instance="/api/v1/thing",
            ),
            status_code=409,
        )
        assert via_public.status_code == via_model.status_code
        assert via_public.media_type == via_model.media_type
        assert json.loads(bytes(via_public.body).decode()) == json.loads(bytes(via_model.body).decode())

    def test_instance_truncation_helper(self) -> None:
        long_instance = "/x?" + ("a" * 5000)
        truncated = truncate_problem_instance(long_instance)
        assert truncated is not None
        assert len(truncated) == 2048
        assert truncate_problem_instance(None) is None
        assert truncate_problem_instance("/short") == "/short"
