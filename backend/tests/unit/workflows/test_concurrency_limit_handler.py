"""Unit tests for workflow_concurrency_limit_handler."""

import json
from unittest.mock import Mock

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.workflows.error_handlers import workflow_concurrency_limit_handler
from syntara.workflows.exceptions import WorkflowConcurrencyLimitError


class TestWorkflowConcurrencyLimitHandler:
    """Tests for workflow_concurrency_limit_handler."""

    def test_returns_429_with_problem_json(self) -> None:
        """Handler returns 429 Too Many Requests with RFC 9457 format."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/executions"

        exc = WorkflowConcurrencyLimitError(limit=10, active=10)
        response = workflow_concurrency_limit_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 429
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["rate_limited"]
        assert data["title"] == "Workflow Concurrency Limit Reached"
        assert data["code"] == "WORKFLOW_CONCURRENCY_LIMIT"
        assert data["retryable"] is True
        assert data["instance"] == "https://api.example.com/executions"

    def test_detail_includes_active_and_limit_counts(self) -> None:
        """Detail message contains the active/limit counts."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/executions"

        exc = WorkflowConcurrencyLimitError(limit=50, active=50)
        response = workflow_concurrency_limit_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert "50/50" in data["detail"]

    def test_is_retryable(self) -> None:
        """Concurrency-limit errors are retryable (caller should back off and retry)."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/executions"

        exc = WorkflowConcurrencyLimitError(limit=5, active=5)
        response = workflow_concurrency_limit_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is True
