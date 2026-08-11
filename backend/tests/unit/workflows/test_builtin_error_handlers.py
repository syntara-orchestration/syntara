"""Unit tests for builtin workflow error handlers."""

import json
from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.workflows.error_handlers import (
    builtin_workflow_delete_handler,
    builtin_workflow_missing_handler,
    builtin_workflow_modify_handler,
)
from syntara.workflows.exceptions import (
    BuiltinWorkflowDeleteError,
    BuiltinWorkflowMissingError,
    BuiltinWorkflowModifyError,
)

_URL = "https://api.example.com/workflows/builtin-1"


def _make_request() -> Mock:
    request = Mock(spec=Request)
    request.url = _URL
    return request


@pytest.mark.parametrize(
    ("handler", "exc", "expected_code", "detail_verb"),
    [
        (
            builtin_workflow_delete_handler,
            BuiltinWorkflowDeleteError("Document Conversion"),
            "BUILTIN_WORKFLOW_DELETE_FORBIDDEN",
            "cannot be deleted",
        ),
        (
            builtin_workflow_modify_handler,
            BuiltinWorkflowModifyError("Document Conversion"),
            "BUILTIN_WORKFLOW_MODIFY_FORBIDDEN",
            "cannot be modified",
        ),
    ],
    ids=["delete", "modify"],
)
class TestBuiltinHandlers:
    """Both builtin error handlers return 403 with RFC 9457 problem details."""

    def test_returns_403_with_rfc9457_format(self, handler, exc, expected_code, detail_verb) -> None:
        response = handler(_make_request(), exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 403
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["forbidden"]
        assert data["title"] == "Forbidden"
        assert data["code"] == expected_code
        assert data["retryable"] is False
        assert data["instance"] == _URL

    def test_detail_includes_workflow_name_and_verb(self, handler, exc, expected_code, detail_verb) -> None:
        response = handler(_make_request(), exc)

        data = json.loads(bytes(response.body).decode())
        assert "Document Conversion" in data["detail"]
        assert detail_verb in data["detail"]


class TestBuiltinWorkflowMissingHandler:
    """Test suite for builtin_workflow_missing_handler."""

    def test_returns_500_with_problem_details(self) -> None:
        exc = BuiltinWorkflowMissingError("Document Conversion")
        response = builtin_workflow_missing_handler(_make_request(), exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["internal_error"]
        assert data["title"] == "System Misconfigured"
        assert data["code"] == "BUILTIN_WORKFLOW_MISSING"
        assert data["retryable"] is True
        assert data["instance"] == _URL
