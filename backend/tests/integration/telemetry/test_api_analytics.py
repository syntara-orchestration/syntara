"""Integration tests for API call telemetry via audit dispatcher.

Verifies that HTTPRequestEvent dispatched by AuditMiddleware triggers
the APICallTelemetryHandler to emit an APICallEvent to Segment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from syntara.api.constants import API_V1_PATH_PREFIX
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.events.http_request import HTTPRequestEvent
from syntara.audit.middleware import AuditMiddleware
from syntara.telemetry.handlers.api_call import APICallTelemetryHandler

if TYPE_CHECKING:
    from syntara.telemetry.events.api_call import APICallEvent

_SETTINGS_PATH = "syntara.telemetry.handlers.api_call.get_settings"
_REGISTRY_PATH = "syntara.telemetry.handlers.api_call.get_telemetry_registry"


def _make_registry_mock() -> MagicMock:
    mock = MagicMock()
    mock.is_initialized.return_value = True
    mock.entitlement_id = ""
    return mock


def _make_settings_mock(*, enabled: bool = True) -> MagicMock:
    mock = MagicMock()
    mock.segment_high_volume_events_enabled = enabled
    return mock


def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with audit middleware for testing."""
    app = FastAPI()

    @app.get("/api/v1/workflows")
    async def list_workflows() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/invocations")
    async def create_invocation() -> dict[str, str]:
        return {"status": "created"}

    @app.get("/api/v1/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict[str, str]:
        return {"id": workflow_id}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/api")
    async def api_discovery() -> dict[str, str]:
        return {"current_version": "/api/v1"}

    @app.get(f"{API_V1_PATH_PREFIX}/docs", include_in_schema=False)
    async def api_v1_docs() -> dict[str, str]:
        return {"docs": "placeholder"}

    app.add_middleware(AuditMiddleware, fastapi_app=app)
    return app


@pytest.fixture
def mock_registry() -> MagicMock:
    """Return a mock TelemetryClientRegistry for testing."""
    return _make_registry_mock()


@pytest.fixture
def test_app() -> FastAPI:
    """Return a FastAPI test app with audit middleware and telemetry handler."""
    AuditEventDispatcher.register({HTTPRequestEvent: APICallTelemetryHandler()})
    return _create_test_app()


class TestEndToEndMiddleware:
    """Test that AuditMiddleware + APICallTelemetryHandler emits api_call events."""

    async def test_get_request_emits_event(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/workflows")

        assert response.status_code == 200

        mock_registry.send_event.assert_called_once()
        event: APICallEvent = mock_registry.send_event.call_args[0][0]
        assert event.endpoint == "/api/v1/workflows"
        assert event.http_method == "GET"
        assert event.status_code == 200
        assert event.response_time_ms >= 0
        assert event.request_payload_size == 0

    async def test_post_request_captures_payload_size(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/invocations",
                    json={"workflow": "test"},
                )

        assert response.status_code == 200

        event: APICallEvent = mock_registry.send_event.call_args[0][0]
        assert event.http_method == "POST"
        assert event.request_payload_size > 0

    async def test_event_contains_all_required_fields(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/workflows")

        event: APICallEvent = mock_registry.send_event.call_args[0][0]
        props = event.model_dump()
        required_fields = {
            "endpoint",
            "http_method",
            "request_id",
            "status_code",
            "response_time_ms",
            "request_payload_size",
            "entitlement_id",
        }
        assert set(props.keys()) == required_fields

    async def test_resource_id_in_endpoint_path(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        workflow_id = "550e8400-e29b-41d4-a716-446655440000"
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get(f"/api/v1/workflows/{workflow_id}")

        event: APICallEvent = mock_registry.send_event.call_args[0][0]
        assert workflow_id in event.endpoint


class TestExcludedPathsIntegration:
    """Test that excluded paths produce no events end-to-end."""

    async def test_health_check_no_event(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

        assert response.status_code == 200
        mock_registry.send_event.assert_not_called()

    async def test_api_discovery_no_event(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api")

        assert response.status_code == 200
        mock_registry.send_event.assert_not_called()

    async def test_docs_no_event(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get(f"{API_V1_PATH_PREFIX}/docs")

        mock_registry.send_event.assert_not_called()


class TestUnmatchedRoutes:
    """Test 404 responses still generate analytics events."""

    async def test_404_generates_event(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/nonexistent")

        assert response.status_code == 404

        mock_registry.send_event.assert_called_once()
        event: APICallEvent = mock_registry.send_event.call_args[0][0]
        assert event.status_code == 404
        assert event.endpoint == "/api/v1/nonexistent"


class TestPrivacyIntegration:
    """Test privacy guarantees end-to-end."""

    async def test_sensitive_headers_not_in_event(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get(
                    "/api/v1/workflows",
                    headers={"Authorization": "Bearer secret-token-xyz"},
                )

        event: APICallEvent = mock_registry.send_event.call_args[0][0]
        props = event.model_dump()
        all_values_str = str(props)
        assert "secret-token" not in all_values_str
        assert "Bearer" not in all_values_str

    async def test_query_params_not_in_event(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/workflows?name=John&token=secret")

        event: APICallEvent = mock_registry.send_event.call_args[0][0]
        props = event.model_dump()
        all_values_str = str(props)
        assert "John" not in all_values_str
        assert "secret" not in all_values_str

    async def test_request_body_not_in_event(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/api/v1/invocations",
                    json={"username": "john_doe", "password": "secret123"},
                )

        event: APICallEvent = mock_registry.send_event.call_args[0][0]
        props = event.model_dump()
        all_values_str = str(props)
        assert "john_doe" not in all_values_str
        assert "secret123" not in all_values_str
        assert event.request_payload_size > 0


class TestErrorResilienceIntegration:
    """Test that analytics failures don't affect API operation."""

    async def test_api_works_when_analytics_fails(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        mock_registry.send_event.side_effect = RuntimeError("Segment down")

        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/workflows")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_multiple_requests_work_with_failing_analytics(
        self, test_app: FastAPI, mock_registry: MagicMock
    ) -> None:
        mock_registry.send_event.side_effect = RuntimeError("Segment down")

        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for _ in range(5):
                    response = await client.get("/api/v1/workflows")
                    assert response.status_code == 200


class TestHighVolumeEventsDisabled:
    """Test that api_call events are suppressed when the flag is off."""

    async def test_no_event_emitted_when_disabled(self, test_app: FastAPI, mock_registry: MagicMock) -> None:
        transport = ASGITransport(app=test_app)
        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=False)),
            patch(_REGISTRY_PATH, return_value=mock_registry),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/workflows")

        assert response.status_code == 200
        mock_registry.send_event.assert_not_called()
