"""Fixtures specific to workflow integration tests.

Provides mock HTTP server using respx for API activity testing.
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, PropertyMock, patch
from uuid import uuid4

import httpx
import pytest
import respx
from httpx import Response

from syntara.core.config.base import Settings
from syntara.core.models import User


@pytest.fixture(autouse=True)
def _mock_service_identity() -> Generator[None, None, None]:
    """Provide a service_identity for tests running without S2S TLS certificates."""
    with patch.object(Settings, "service_identity", new_callable=PropertyMock, return_value="backend.ao.svc"):
        yield


_FAKE_USER = User(
    id=uuid4(),
    username="ws-test-bypass",
    email="ws-test-bypass@example.com",
    first_name="Test",
    is_enabled=True,
)


@pytest.fixture(autouse=True)
def _bypass_websocket_auth() -> Generator[None, None, None]:
    """Bypass WebSocket auth and authz guards for workflow integration tests."""
    with (
        patch(
            "syntara.core.websocket.endpoint_factory._authenticate_websocket",
            AsyncMock(return_value=_FAKE_USER),
        ),
        patch(
            "syntara.core.websocket.endpoint_factory._check_websocket_authorization",
            AsyncMock(return_value=True),
        ),
    ):
        yield


@pytest.fixture
def mock_api_server() -> Generator[respx.MockRouter, None, None]:
    """Provide a mock HTTP server for API activity tests using respx.

    The mock server automatically intercepts all httpx requests and returns
    configured responses. Provides a clean API for configuring responses and
    asserting on requests.

    Yields:
        respx.MockRouter: Router for configuring mock responses

    Example:
        >>> # Configure responses
        >>> mock_api_server.get("http://test-api.example.com/api/data").mock(
        ...     return_value=Response(200, json={"items": [1, 2, 3]})
        ... )
        >>> mock_api_server.post("http://test-api.example.com/api/users").mock(
        ...     return_value=Response(201, json={"id": "123"})
        ... )
        >>>
        >>> # Assert on requests after test
        >>> assert mock_api_server.routes["get_data"].called
        >>> assert mock_api_server.routes["get_data"].call_count == 1

    """
    with respx.mock(base_url="http://test-api.example.com", assert_all_called=False) as respx_mock:
        # Configure default successful responses for common paths
        # GET endpoints
        respx_mock.get("/api/data").mock(return_value=Response(200, json={"data": "test", "items": []}))
        respx_mock.get("/api/users").mock(return_value=Response(200, json={"users": []}))
        respx_mock.get("/api/auth").mock(return_value=Response(200, json={"authenticated": True}))

        # POST endpoints
        respx_mock.post("/api/create").mock(return_value=Response(201, json={"id": "123", "created": True}))
        respx_mock.post("/api/users").mock(return_value=Response(201, json={"id": "user-123", "name": "Test User"}))

        # PUT endpoints
        respx_mock.put("/api/users/123").mock(return_value=Response(200, json={"id": "123", "updated": True}))
        respx_mock.put("/api/resource/456").mock(return_value=Response(200, json={"success": True}))

        # PATCH endpoints
        respx_mock.patch("/api/users/123").mock(return_value=Response(200, json={"id": "123", "patched": True}))

        # DELETE endpoints
        respx_mock.delete("/api/users/123").mock(return_value=Response(204))
        respx_mock.delete("/api/resource/456").mock(return_value=Response(200, json={"deleted": True}))

        # Special endpoints for testing error conditions
        respx_mock.get("/api/error").mock(return_value=Response(500, json={"error": "Internal Server Error"}))
        respx_mock.get("/api/notfound").mock(return_value=Response(404, json={"error": "Not Found"}))

        # Authentication endpoints - verify headers are set correctly
        def check_bearer_auth(request: httpx.Request) -> Response:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return Response(200, json={"authenticated": True, "auth_type": "bearer"})
            return Response(401, json={"error": "Unauthorized"})

        def check_basic_auth(request: httpx.Request) -> Response:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Basic "):
                return Response(200, json={"authenticated": True, "auth_type": "basic"})
            return Response(401, json={"error": "Unauthorized"})

        def check_apikey_auth(request: httpx.Request) -> Response:
            api_key = request.headers.get("X-API-Key", "")
            if api_key:
                return Response(200, json={"authenticated": True, "auth_type": "apiKey"})
            return Response(401, json={"error": "Unauthorized"})

        def check_oauth2_auth(request: httpx.Request) -> Response:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return Response(200, json={"authenticated": True, "auth_type": "oauth2"})
            return Response(401, json={"error": "Unauthorized"})

        respx_mock.get("/api/protected").mock(side_effect=check_bearer_auth)
        respx_mock.get("/api/basic-auth").mock(side_effect=check_basic_auth)
        respx_mock.get("/api/apikey-auth").mock(side_effect=check_apikey_auth)
        respx_mock.get("/api/oauth-auth").mock(side_effect=check_oauth2_auth)

        # Catch-all for any other requests
        respx_mock.route().mock(return_value=Response(200, json={"success": True}))

        yield respx_mock
