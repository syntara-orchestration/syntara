"""Unit tests for APICallTelemetryHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from syntara.audit.emitter import AuditActorContext
from syntara.audit.events.http_request import HTTPRequestEvent
from syntara.core.models.principal import PrincipalType
from syntara.telemetry.api_usage_accumulator import APIUsageAccumulator
from syntara.telemetry.handlers.api_call import APICallTelemetryHandler


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock()
    registry.is_initialized.return_value = True
    registry.entitlement_id = "ent-test-123"
    registry.installation_salt = "test-salt-abc"
    return registry


@pytest.fixture
def fresh_accumulator() -> APIUsageAccumulator:
    return APIUsageAccumulator()


def _make_event(
    actor_id=None,
    actor_type=None,
    path="/api/v1/workflows",
    method="GET",
    status_code=200,
    interface="api",
    endpoint_template="/api/v1/workflows",
) -> HTTPRequestEvent:
    return HTTPRequestEvent(
        method=method,
        path=path,
        status_code=status_code,
        actor_context=AuditActorContext(
            actor_id=actor_id,
            actor_username="testuser",
            actor_type=actor_type,
        ),
        response_time_ms=42,
        request_payload_size=0,
        interface=interface,
        endpoint_template=endpoint_template,
    )


class TestRecordUsage:
    """Tests for the _record_usage static method (accumulator feeding)."""

    def test_records_authenticated_request(self, mock_registry: MagicMock, fresh_accumulator: APIUsageAccumulator):
        actor_id = uuid4()
        event = _make_event(actor_id=actor_id, actor_type=PrincipalType.USER)

        with (
            patch("syntara.telemetry.handlers.api_call.get_telemetry_registry", return_value=mock_registry),
            patch("syntara.telemetry.handlers.api_call.get_accumulator", return_value=fresh_accumulator),
        ):
            APICallTelemetryHandler._record_usage(event)

        snapshot = fresh_accumulator.drain()
        assert len(snapshot.caller_ids) == 1
        assert snapshot.callers_by_type == {"user": 1}
        assert snapshot.callers_by_interface == {"api": 1}
        assert snapshot.feature_usage[("/api/v1/workflows", "GET", "api")] == 1

    def test_skips_unauthenticated_request(self, mock_registry: MagicMock, fresh_accumulator: APIUsageAccumulator):
        event = _make_event(actor_id=None)

        with (
            patch("syntara.telemetry.handlers.api_call.get_telemetry_registry", return_value=mock_registry),
            patch("syntara.telemetry.handlers.api_call.get_accumulator", return_value=fresh_accumulator),
        ):
            APICallTelemetryHandler._record_usage(event)

        snapshot = fresh_accumulator.drain()
        assert len(snapshot.caller_ids) == 0

    def test_uses_endpoint_template_over_path(self, mock_registry: MagicMock, fresh_accumulator: APIUsageAccumulator):
        event = _make_event(
            actor_id=uuid4(),
            actor_type=PrincipalType.USER,
            path="/api/v1/workflows/abc-123",
            endpoint_template="/api/v1/workflows/{workflow_id}",
        )

        with (
            patch("syntara.telemetry.handlers.api_call.get_telemetry_registry", return_value=mock_registry),
            patch("syntara.telemetry.handlers.api_call.get_accumulator", return_value=fresh_accumulator),
        ):
            APICallTelemetryHandler._record_usage(event)

        snapshot = fresh_accumulator.drain()
        assert ("/api/v1/workflows/{workflow_id}", "GET", "api") in snapshot.feature_usage

    def test_skips_when_no_endpoint_template(self, mock_registry: MagicMock, fresh_accumulator: APIUsageAccumulator):
        event = _make_event(
            actor_id=uuid4(),
            actor_type=PrincipalType.USER,
            path="/api/v1/unknown",
            endpoint_template=None,
        )

        with (
            patch("syntara.telemetry.handlers.api_call.get_telemetry_registry", return_value=mock_registry),
            patch("syntara.telemetry.handlers.api_call.get_accumulator", return_value=fresh_accumulator),
        ):
            APICallTelemetryHandler._record_usage(event)

        snapshot = fresh_accumulator.drain()
        assert len(snapshot.caller_ids) == 0
        assert len(snapshot.feature_usage) == 0

    def test_records_service_account_type(self, mock_registry: MagicMock, fresh_accumulator: APIUsageAccumulator):
        event = _make_event(
            actor_id=uuid4(),
            actor_type=PrincipalType.SERVICE_ACCOUNT,
        )

        with (
            patch("syntara.telemetry.handlers.api_call.get_telemetry_registry", return_value=mock_registry),
            patch("syntara.telemetry.handlers.api_call.get_accumulator", return_value=fresh_accumulator),
        ):
            APICallTelemetryHandler._record_usage(event)

        snapshot = fresh_accumulator.drain()
        assert snapshot.callers_by_type == {"service_account": 1}

    def test_records_ui_interface(self, mock_registry: MagicMock, fresh_accumulator: APIUsageAccumulator):
        event = _make_event(
            actor_id=uuid4(),
            actor_type=PrincipalType.USER,
            interface="ui",
        )

        with (
            patch("syntara.telemetry.handlers.api_call.get_telemetry_registry", return_value=mock_registry),
            patch("syntara.telemetry.handlers.api_call.get_accumulator", return_value=fresh_accumulator),
        ):
            APICallTelemetryHandler._record_usage(event)

        snapshot = fresh_accumulator.drain()
        assert snapshot.callers_by_interface == {"ui": 1}

    def test_does_not_raise_on_accumulator_error(self, mock_registry: MagicMock):
        event = _make_event(actor_id=uuid4(), actor_type=PrincipalType.USER)

        mock_acc = MagicMock()
        mock_acc.record.side_effect = RuntimeError("boom")

        with (
            patch("syntara.telemetry.handlers.api_call.get_telemetry_registry", return_value=mock_registry),
            patch("syntara.telemetry.handlers.api_call.get_accumulator", return_value=mock_acc),
        ):
            APICallTelemetryHandler._record_usage(event)

    def test_does_not_raise_on_registry_error(self):
        event = _make_event(actor_id=uuid4(), actor_type=PrincipalType.USER)

        with patch(
            "syntara.telemetry.handlers.api_call.get_telemetry_registry",
            side_effect=RuntimeError("registry down"),
        ):
            APICallTelemetryHandler._record_usage(event)

    def test_handles_none_actor_type(self, mock_registry: MagicMock, fresh_accumulator: APIUsageAccumulator):
        event = _make_event(actor_id=uuid4(), actor_type=None)

        with (
            patch("syntara.telemetry.handlers.api_call.get_telemetry_registry", return_value=mock_registry),
            patch("syntara.telemetry.handlers.api_call.get_accumulator", return_value=fresh_accumulator),
        ):
            APICallTelemetryHandler._record_usage(event)

        snapshot = fresh_accumulator.drain()
        assert snapshot.callers_by_type == {"unknown": 1}


class TestHandleMethod:
    """Tests for the top-level handle() method."""

    def test_handle_calls_both_record_and_emit(self, mock_registry: MagicMock):
        event = _make_event(actor_id=uuid4(), actor_type=PrincipalType.USER)

        with (
            patch.object(APICallTelemetryHandler, "_record_usage") as mock_record,
            patch.object(APICallTelemetryHandler, "_emit_api_call_event") as mock_emit,
        ):
            result = APICallTelemetryHandler().handle(event)

        assert result is None
        mock_record.assert_called_once_with(event)
        mock_emit.assert_called_once_with(event)

    def test_handle_returns_none(self):
        event = _make_event()

        with (
            patch.object(APICallTelemetryHandler, "_record_usage"),
            patch.object(APICallTelemetryHandler, "_emit_api_call_event"),
        ):
            result = APICallTelemetryHandler().handle(event)

        assert result is None
