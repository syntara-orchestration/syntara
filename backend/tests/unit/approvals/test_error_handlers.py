"""Unit tests for approval error handlers."""

import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.approvals.error_handlers import (
    approval_already_decided_handler,
    approval_already_requested_handler,
    approval_not_found_handler,
)
from syntara.approvals.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalAlreadyRequestedError,
    ApprovalNotFoundError,
)
from syntara.approvals.models import ApprovalRequestStatus
from syntara.core.error_handlers import PROBLEM_TYPES


class TestApprovalNotFoundHandler:
    """Test suite for approval_not_found_handler."""

    def test_handles_approval_not_found_error(self) -> None:
        """Test handling of ApprovalNotFoundError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/12345678-1234-1234-1234-123456789012"

        approval_id = uuid4()
        exc = ApprovalNotFoundError(approval_id)
        response = approval_not_found_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Approval Not Found"
        assert data["detail"] == "The requested approval was not found"
        assert data["code"] == "APPROVAL_NOT_FOUND"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/api/v1/approvals/12345678-1234-1234-1234-123456789012"

    def test_preserves_request_url(self) -> None:
        """Test that request URL is preserved in instance field."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/99999999-9999-9999-9999-999999999999"

        approval_id = uuid4()
        exc = ApprovalNotFoundError(approval_id)
        response = approval_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == "https://api.example.com/api/v1/approvals/99999999-9999-9999-9999-999999999999"

    def test_not_retryable(self) -> None:
        """Test that approval not found errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/test"

        approval_id = uuid4()
        exc = ApprovalNotFoundError(approval_id)
        response = approval_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False

    def test_uses_correct_http_status(self) -> None:
        """Test that handler returns 404 status code."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/test"

        approval_id = uuid4()
        exc = ApprovalNotFoundError(approval_id)
        response = approval_not_found_handler(request, exc)

        assert response.status_code == 404

    def test_uses_correct_problem_type(self) -> None:
        """Test that handler uses resource_not_found problem type."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/test"

        approval_id = uuid4()
        exc = ApprovalNotFoundError(approval_id)
        response = approval_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]

    @pytest.mark.parametrize(
        ("url", "expected_instance"),
        [
            (
                "https://api.example.com/api/v1/approvals/123e4567-e89b-12d3-a456-426614174000",
                "https://api.example.com/api/v1/approvals/123e4567-e89b-12d3-a456-426614174000",
            ),
            (
                "http://localhost:8000/api/v1/approvals/987fcdeb-51a2-43d7-8f6e-123456789abc",
                "http://localhost:8000/api/v1/approvals/987fcdeb-51a2-43d7-8f6e-123456789abc",
            ),
            (
                "https://api.com/api/v1/approvals/456?include=context",
                "https://api.com/api/v1/approvals/456?include=context",
            ),
        ],
    )
    def test_various_request_urls(self, url: str, expected_instance: str) -> None:
        """Test handling of various request URL formats."""
        request = Mock(spec=Request)
        request.url = url

        approval_id = uuid4()
        exc = ApprovalNotFoundError(approval_id)
        response = approval_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == expected_instance


class TestApprovalAlreadyDecidedHandler:
    """Test suite for approval_already_decided_handler."""

    def test_handles_approval_already_decided_error(self) -> None:
        """Test handling of ApprovalAlreadyDecidedError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/12345678-1234-1234-1234-123456789012"

        approval_id = uuid4()
        exc = ApprovalAlreadyDecidedError(approval_id, ApprovalRequestStatus.APPROVED)
        response = approval_already_decided_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_conflict"]
        assert data["title"] == "Approval Already Decided"
        assert data["detail"] == "The approval request has already been decided and cannot be modified"
        assert data["code"] == "APPROVAL_ALREADY_DECIDED"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/api/v1/approvals/12345678-1234-1234-1234-123456789012"

    def test_preserves_request_url(self) -> None:
        """Test that request URL is preserved in instance field."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/99999999-9999-9999-9999-999999999999"

        approval_id = uuid4()
        exc = ApprovalAlreadyDecidedError(approval_id, ApprovalRequestStatus.REJECTED)
        response = approval_already_decided_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == "https://api.example.com/api/v1/approvals/99999999-9999-9999-9999-999999999999"

    def test_not_retryable(self) -> None:
        """Test that approval already decided errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/test"

        approval_id = uuid4()
        exc = ApprovalAlreadyDecidedError(approval_id, ApprovalRequestStatus.APPROVED)
        response = approval_already_decided_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False

    def test_uses_correct_http_status(self) -> None:
        """Test that handler returns 409 status code."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/test"

        approval_id = uuid4()
        exc = ApprovalAlreadyDecidedError(approval_id, ApprovalRequestStatus.CANCELLED)
        response = approval_already_decided_handler(request, exc)

        assert response.status_code == 409

    def test_uses_correct_problem_type(self) -> None:
        """Test that handler uses resource_conflict problem type."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/test"

        approval_id = uuid4()
        exc = ApprovalAlreadyDecidedError(approval_id, ApprovalRequestStatus.APPROVED)
        response = approval_already_decided_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_conflict"]

    @pytest.mark.parametrize(
        ("status", "url", "expected_instance"),
        [
            (
                ApprovalRequestStatus.APPROVED,
                "https://api.example.com/api/v1/approvals/123e4567-e89b-12d3-a456-426614174000",
                "https://api.example.com/api/v1/approvals/123e4567-e89b-12d3-a456-426614174000",
            ),
            (
                ApprovalRequestStatus.REJECTED,
                "http://localhost:8000/api/v1/approvals/987fcdeb-51a2-43d7-8f6e-123456789abc",
                "http://localhost:8000/api/v1/approvals/987fcdeb-51a2-43d7-8f6e-123456789abc",
            ),
            (
                ApprovalRequestStatus.CANCELLED,
                "https://api.com/api/v1/approvals/456?notes=test",
                "https://api.com/api/v1/approvals/456?notes=test",
            ),
        ],
    )
    def test_various_request_urls_and_statuses(
        self, status: ApprovalRequestStatus, url: str, expected_instance: str
    ) -> None:
        """Test handling of various request URL formats and decision statuses."""
        request = Mock(spec=Request)
        request.url = url

        approval_id = uuid4()
        exc = ApprovalAlreadyDecidedError(approval_id, status)
        response = approval_already_decided_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == expected_instance

    def test_error_detail_is_consistent(self) -> None:
        """Test that error detail message is consistent regardless of approval status."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals/test"

        approval_id = uuid4()

        # Test with different statuses
        for status in [ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED, ApprovalRequestStatus.CANCELLED]:
            exc = ApprovalAlreadyDecidedError(approval_id, status)
            response = approval_already_decided_handler(request, exc)

            data = json.loads(bytes(response.body).decode())
            assert data["detail"] == "The approval request has already been decided and cannot be modified"


class TestApprovalAlreadyRequestedHandler:
    """Test suite for approval_already_requested_handler."""

    def test_handles_approval_already_requested_error(self) -> None:
        """Test handling of ApprovalAlreadyRequestedError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/api/v1/approvals"

        execution_id = uuid4()
        approval_node_id = "approval_task_1"
        exc = ApprovalAlreadyRequestedError(execution_id, approval_node_id)
        response = approval_already_requested_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_conflict"]
        assert data["title"] == "Approval Already Requested"
        assert data["detail"] == "An approval request already exists for this execution and approval node"
        assert data["code"] == "APPROVAL_ALREADY_REQUESTED"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/api/v1/approvals"
