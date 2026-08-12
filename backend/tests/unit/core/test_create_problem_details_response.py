"""Unit tests for create_problem_details_response utility function."""

import json

import pytest
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response


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
