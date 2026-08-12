"""Unit tests for _ValidationRoute — RequestValidationError → RFC 9457 problem response."""

import json
from unittest.mock import Mock, patch

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from syntara.workflows.router import _ValidationRoute


class TestValidationRouteHandler:
    """Tests for _ValidationRoute error handling of malformed request bodies."""

    @pytest.mark.asyncio
    async def test_converts_request_validation_error_to_problem_response(self) -> None:
        """RequestValidationError is caught and returned as RFC 9457 with ValidationResult."""
        errors = [
            {"loc": ("body", "workflow_definition"), "msg": "Field required", "type": "missing"},
        ]

        async def mock_handler(request: Request) -> None:
            raise RequestValidationError(errors)

        route = _ValidationRoute(path="/validate", endpoint=lambda: None, methods=["POST"])

        with patch.object(APIRoute, "get_route_handler", return_value=mock_handler):
            handler = route.get_route_handler()

        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/validate"

        response = await handler(request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["validation_result"]["is_valid"] is False
        assert data["validation_result"]["error_count"] == 1
        findings = data["validation_result"]["findings"]
        assert len(findings) == 1
        assert findings[0]["severity"] == "error"
        assert findings[0]["category"] == "schema_violation"
        assert "workflow_definition" in findings[0]["message"]

    @pytest.mark.asyncio
    async def test_strips_body_prefix_from_path(self) -> None:
        """The 'body' prefix in validation error location paths is removed."""
        errors = [
            {"loc": ("body", "workflow_definition", "nodes", 0, "type"), "msg": "Invalid", "type": "value_error"},
        ]

        async def mock_handler(request: Request) -> None:
            raise RequestValidationError(errors)

        route = _ValidationRoute(path="/validate", endpoint=lambda: None, methods=["POST"])

        with patch.object(APIRoute, "get_route_handler", return_value=mock_handler):
            handler = route.get_route_handler()

        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/validate"

        response = await handler(request)
        data = json.loads(bytes(response.body).decode())
        msg = data["validation_result"]["findings"][0]["message"]
        assert msg.startswith("workflow_definition")
        assert "body" not in msg.split(":")[0]

    @pytest.mark.asyncio
    async def test_passes_through_successful_response(self) -> None:
        """Normal responses are returned without modification."""
        expected = JSONResponse(content={"ok": True})

        async def mock_handler(request: Request) -> JSONResponse:
            return expected

        route = _ValidationRoute(path="/validate", endpoint=lambda: None, methods=["POST"])

        with patch.object(APIRoute, "get_route_handler", return_value=mock_handler):
            handler = route.get_route_handler()

        request = Mock(spec=Request)
        response = await handler(request)
        assert response is expected
