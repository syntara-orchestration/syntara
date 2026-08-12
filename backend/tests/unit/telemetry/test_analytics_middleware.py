"""Unit tests for APICallTelemetryHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from syntara.audit.emitter import AuditActorContext
from syntara.audit.events.http_request import HTTPRequestEvent
from syntara.telemetry.events.api_call import APICallEvent
from syntara.telemetry.handlers.api_call import APICallTelemetryHandler

_SETTINGS_PATH = "syntara.telemetry.handlers.api_call.get_settings"
_REGISTRY_PATH = "syntara.telemetry.handlers.api_call.get_telemetry_registry"


def _make_http_event(
    method: str = "GET",
    path: str = "/api/v1/test",
    status_code: int = 200,
    response_time_ms: int = 42,
    request_payload_size: int = 0,
) -> HTTPRequestEvent:
    return HTTPRequestEvent(
        method=method,
        path=path,
        status_code=status_code,
        response_time_ms=response_time_ms,
        request_payload_size=request_payload_size,
        actor_context=AuditActorContext(),
    )


def _make_registry_mock() -> MagicMock:
    mock = MagicMock()
    mock.is_initialized.return_value = True
    mock.entitlement_id = ""
    return mock


def _make_settings_mock(*, enabled: bool = True) -> MagicMock:
    mock = MagicMock()
    mock.segment_high_volume_events_enabled = enabled
    return mock


class TestAPICallTelemetryHandlerEmission:
    """Test that the handler emits api_call events."""

    def test_emits_event_on_normal_request(self) -> None:
        registry = _make_registry_mock()
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            result = handler.handle(_make_http_event())

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, APICallEvent)
        assert event.endpoint == "/api/v1/test"
        assert event.http_method == "GET"
        assert event.status_code == 200

    def test_captures_status_code(self) -> None:
        registry = _make_registry_mock()
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            handler.handle(_make_http_event(status_code=500))

        event = registry.send_event.call_args[0][0]
        assert event.status_code == 500

    def test_passes_response_time(self) -> None:
        registry = _make_registry_mock()
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            handler.handle(_make_http_event(response_time_ms=123))

        event = registry.send_event.call_args[0][0]
        assert event.response_time_ms == 123

    def test_passes_payload_size(self) -> None:
        registry = _make_registry_mock()
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            handler.handle(_make_http_event(method="POST", request_payload_size=1024))

        event = registry.send_event.call_args[0][0]
        assert event.request_payload_size == 1024

    def test_zero_payload_size_by_default(self) -> None:
        registry = _make_registry_mock()
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            handler.handle(_make_http_event())

        event = registry.send_event.call_args[0][0]
        assert event.request_payload_size == 0


class TestAPICallTelemetryHandlerSkips:
    """Test that the handler skips when telemetry is not initialized."""

    def test_skips_when_not_initialized(self) -> None:
        registry = _make_registry_mock()
        registry.is_initialized.return_value = False
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            result = handler.handle(_make_http_event())

        assert result is None
        registry.send_event.assert_not_called()


class TestAPICallTelemetryHandlerPrivacy:
    """Test that only allowed fields are present in the event."""

    def test_event_has_only_allowed_fields(self) -> None:
        registry = _make_registry_mock()
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            handler.handle(_make_http_event())

        event = registry.send_event.call_args[0][0]
        props = event.model_dump()
        assert set(props.keys()) == {
            "endpoint",
            "http_method",
            "status_code",
            "response_time_ms",
            "request_payload_size",
            "entitlement_id",
            "request_id",
        }


class TestAPICallTelemetryHandlerResilience:
    """Test fire-and-forget behavior."""

    def test_does_not_raise_when_send_fails(self) -> None:
        registry = _make_registry_mock()
        registry.send_event.side_effect = RuntimeError("Segment unavailable")
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            result = handler.handle(_make_http_event())

        assert result is None

    def test_failure_is_logged_as_warning(self) -> None:
        registry = _make_registry_mock()
        registry.send_event.side_effect = RuntimeError("Segment unavailable")
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=True)),
            patch(_REGISTRY_PATH, return_value=registry),
            patch("syntara.telemetry.handlers.api_call.logger") as mock_logger,
        ):
            handler.handle(_make_http_event())
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "analytics_event_failed" in call_args[0]


class TestAPICallTelemetryHandlerDisabledByDefault:
    """Test that high-volume api_call events are suppressed by default."""

    def test_no_event_emitted_when_disabled(self) -> None:
        registry = _make_registry_mock()
        handler = APICallTelemetryHandler()

        with (
            patch(_SETTINGS_PATH, return_value=_make_settings_mock(enabled=False)),
            patch(_REGISTRY_PATH, return_value=registry),
        ):
            result = handler.handle(_make_http_event())

        assert result is None
        registry.send_event.assert_not_called()
