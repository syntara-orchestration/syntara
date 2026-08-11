"""Integration tests for malformed cursor handling across API endpoints.

Tests the end-to-end functionality for handling malformed cursor tokens
through various HTTP API endpoints, ensuring proper error responses.
"""

import pytest
from httpx import AsyncClient

from syntara.core.error_handlers import PROBLEM_TYPES


class TestMalformedCursorHandling:
    """Integration tests for malformed cursor handling across API endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/v1/tools",
            "/api/v1/workflows",
            "/api/v1/executions",
            "/api/v1/invocations",
        ],
    )
    async def test_malformed_cursor_returns_422_error(
        self,
        jwt_client: AsyncClient,
        endpoint: str,
    ) -> None:
        """Test that malformed cursor in API endpoints returns 422 Unprocessable Entity."""
        # Test with a malformed cursor that contains invalid base64 characters
        malformed_cursor = "invalid_base64!!!!"

        # Make request to the endpoint with malformed cursor
        response = await jwt_client.get(endpoint, params={"cursor": malformed_cursor})

        # Should return 422 Unprocessable Entity for malformed cursor
        assert response.status_code == 422

        data = response.json()
        assert data["type"] == PROBLEM_TYPES["validation_error"]
        assert data["title"] == "Validation Error"
        assert "Invalid cursor format: Invalid base64-encoded string" in data["detail"]
        assert data["code"] == "VALIDATION_ERROR"
        assert data["retryable"] is False
        assert data["instance"] == f"http://test{endpoint}?cursor=invalid_base64%21%21%21%21"
