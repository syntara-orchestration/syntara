"""Audit keeps provenance while anonymous retry telemetry excludes it."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.handlers.retry_requested import RetryRequestedTelemetryHandler
from syntara.workflows.audit.retry_requested import RetryRequestedEvent, RetryRequestedHandler


def test_retry_audit_and_anonymous_telemetry() -> None:
    """Identifying retry context stays in audit, never in telemetry properties."""
    event = RetryRequestedEvent(
        execution_id=uuid4(),
        source_execution_id=uuid4(),
        workflow_id=uuid4(),
        triggered_by=uuid4(),
        selected_point_ids=["failed-node"],
        node_count=5,
        failed_step_types=["script"],
    )
    audit = RetryRequestedHandler().handle(event)
    assert audit.execution_id == event.execution_id
    assert audit.structured_data is not None
    data = audit.structured_data.model_dump()
    assert data["source_execution_id"] == str(event.source_execution_id)
    assert data["selected_point_ids"] == ["failed-node"]
    registry = MagicMock(entitlement_id="installation")
    with patch("syntara.telemetry.handlers.retry_requested.get_telemetry_registry", return_value=registry):
        RetryRequestedTelemetryHandler().handle(event)
    payload = registry.send_event.call_args.args[0].model_dump()
    assert payload["execution_mode"] == "retry"
    assert payload["node_count"] == 5
    assert payload["failed_step_types"] == ["script"]
    assert "failed-node" not in str(payload)
    assert str(event.triggered_by) not in str(payload)
    assert str(event.source_execution_id) not in str(payload)
