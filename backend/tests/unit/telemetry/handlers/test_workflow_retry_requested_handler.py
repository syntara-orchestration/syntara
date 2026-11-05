"""Unit tests for accepted retry telemetry payloads."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from syntara.telemetry.events.workflow_execution import WorkflowRetryRequestedEvent
from syntara.telemetry.handlers.workflow_retry_requested import WorkflowRetryRequestedTelemetryHandler
from syntara.workflows.audit.retry_requested import WorkflowRetryRequestedEvent as DomainRetryRequestedEvent


@pytest.mark.parametrize(
    ("retry_kind", "node_count", "failed_step_types"),
    [
        ("standard", None, []),
        ("from_failure", 4, ["http_request", "script"]),
    ],
)
def test_handler_emits_complete_retry_payload(
    retry_kind: str,
    node_count: int | None,
    failed_step_types: list[str],
) -> None:
    """The handler forwards both retry kinds and bounded failure context."""
    registry = MagicMock()
    registry.is_initialized.return_value = True
    registry.entitlement_id = "entitlement"
    event = DomainRetryRequestedEvent(
        execution_id=uuid4(),
        source_execution_id=uuid4(),
        retry_kind=retry_kind,
        node_count=node_count,
        failed_step_types=failed_step_types,
        request_id=uuid4(),
    )

    with patch(
        "syntara.telemetry.handlers.workflow_retry_requested.get_telemetry_registry",
        return_value=registry,
    ):
        WorkflowRetryRequestedTelemetryHandler().handle(event)

    registry.send_event.assert_called_once()
    payload = registry.send_event.call_args.args[0]
    assert isinstance(payload, WorkflowRetryRequestedEvent)
    assert payload.execution_id == event.execution_id
    assert payload.source_execution_id == event.source_execution_id
    assert payload.retry_kind == retry_kind
    assert payload.node_count == node_count
    assert payload.failed_step_types == failed_step_types
    assert payload.request_id == event.request_id


def test_handler_bounds_failed_step_types() -> None:
    """The handler enforces the telemetry payload size limit."""
    registry = MagicMock()
    registry.is_initialized.return_value = True
    registry.entitlement_id = "entitlement"
    event = DomainRetryRequestedEvent(
        execution_id=uuid4(),
        source_execution_id=uuid4(),
        retry_kind="from_failure",
        failed_step_types=[f"type_{index}" for index in range(60)],
    )

    with patch(
        "syntara.telemetry.handlers.workflow_retry_requested.get_telemetry_registry",
        return_value=registry,
    ):
        WorkflowRetryRequestedTelemetryHandler().handle(event)

    payload = registry.send_event.call_args.args[0]
    assert len(payload.failed_step_types) == 50
