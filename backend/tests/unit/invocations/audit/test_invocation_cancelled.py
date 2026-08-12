"""Unit tests for InvocationCancelledEvent and InvocationCancelledHandler."""

from uuid import uuid4

from syntara.agent_orchestrator.models import InvocationStatus
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.invocations.audit.invocation_cancelled import (
    InvocationCancellationResult,
    InvocationCancelledEvent,
    InvocationCancelledHandler,
)


class TestInvocationCancelledEvent:
    """Tests for InvocationCancelledEvent dataclass."""

    def test_minimal_construction_defaults(self) -> None:
        """InvocationCancelledEvent can be constructed with minimal required fields; defaults apply."""
        invocation_id = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.SUCCESS,
            reason="User cancelled",
        )
        assert event.invocation_id == invocation_id
        assert event.result == InvocationCancellationResult.SUCCESS
        assert event.reason == "User cancelled"
        assert event.files_cleaned == []
        assert event.current_status is None
        assert event.error_type is None

    def test_enrichment_with_files_cleaned(self) -> None:
        """InvocationCancelledEvent can include files_cleaned list."""
        invocation_id = uuid4()
        file_id_1 = uuid4()
        file_id_2 = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.SUCCESS,
            reason="Cleanup test",
            files_cleaned=[file_id_1, file_id_2],
            current_status=InvocationStatus.CANCELLED,
        )
        assert event.files_cleaned == [file_id_1, file_id_2]
        assert event.current_status == InvocationStatus.CANCELLED

    def test_error_type_can_be_set(self) -> None:
        """error_type can be set for technical failures."""
        invocation_id = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.SUCCESS,
            reason="Test",
            error_type="SQLAlchemyError",
        )
        assert event.error_type == "SQLAlchemyError"


class TestInvocationCancelledHandler:
    """Tests for InvocationCancelledHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """InvocationCancelledHandler is a subclass of AuditEventHandler."""
        assert issubclass(InvocationCancelledHandler, AuditEventHandler)

    def test_successful_cancellation(self) -> None:
        """Successful cancellation produces USER_ACTION / INFO / SUCCESS / 'invocation_cancelled' event."""
        invocation_id = uuid4()
        file_id_1 = uuid4()
        file_id_2 = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.SUCCESS,
            reason="User requested cancellation",
            files_cleaned=[file_id_1, file_id_2],
            current_status=InvocationStatus.CANCELLED,
        )
        handler = InvocationCancelledHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "invocation_cancelled"
        assert result.source_component == "syntara.invocations.cancel"
        assert result.event_message == "Invocation cancelled: User requested cancellation"
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        # Without activity context, resource_name should be None
        assert result.resource_name is None

    def test_successful_cancellation_structured_data(self) -> None:
        """Successful cancellation includes files_cleaned in structured_data."""
        invocation_id = uuid4()
        file_id_1 = uuid4()
        file_id_2 = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.SUCCESS,
            reason="Cleanup test",
            files_cleaned=[file_id_1, file_id_2],
            current_status=InvocationStatus.CANCELLED,
        )
        handler = InvocationCancelledHandler()
        result = handler.handle(event)

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "invocation-cancelled-context"
        assert result.structured_data.invocation_id == invocation_id  # type: ignore[attr-defined]
        assert result.structured_data.cancellation_result == "success"  # type: ignore[attr-defined]
        assert result.structured_data.cancellation_reason == "Cleanup test"  # type: ignore[attr-defined]
        assert result.structured_data.files_cleaned == [file_id_1, file_id_2]  # type: ignore[attr-defined]
        assert result.structured_data.current_status == InvocationStatus.CANCELLED  # type: ignore[attr-defined]
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_not_found_cancellation(self) -> None:
        """NOT_FOUND cancellation produces USER_ACTION / WARNING / ERROR event."""
        invocation_id = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.NOT_FOUND,
            reason="User cancelled",
        )
        handler = InvocationCancelledHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "invocation_cancelled"
        assert result.event_message == "Invocation cancellation failed (not found)"
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_message == "Invocation cancellation failed (not found)"
        assert result.structured_data.error_type is None

    def test_not_cancellable_with_status(self) -> None:
        """NOT_CANCELLABLE cancellation includes current_status in message."""
        invocation_id = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.NOT_CANCELLABLE,
            reason="User cancelled",
            current_status=InvocationStatus.COMPLETED,
        )
        handler = InvocationCancelledHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "invocation_cancelled"
        assert result.event_message == f"Invocation cancellation failed (status: {InvocationStatus.COMPLETED})"
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.current_status == InvocationStatus.COMPLETED  # type: ignore[attr-defined]
        assert (
            result.structured_data.error_message
            == f"Invocation cancellation failed (status: {InvocationStatus.COMPLETED})"
        )

    def test_technical_error(self) -> None:
        """Technical error produces SYSTEM_OPERATION / ERROR / ERROR event."""
        invocation_id = uuid4()
        file_id = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.SUCCESS,
            reason="Test cancellation",
            files_cleaned=[file_id],
            error_type="SQLAlchemyError",
        )
        handler = InvocationCancelledHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SYSTEM_OPERATION
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "invocation_cancelled"
        assert result.event_message == "Invocation cancellation failed due to system error"
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "SQLAlchemyError"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    def test_invocation_cancelled_includes_activity_context(self) -> None:
        """InvocationCancelledEvent includes activity_id and activity_name from workflow context."""
        invocation_id = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.SUCCESS,
            reason="User cancelled workflow",
            activity_id="activity-789",
            activity_name="approval_flow",
        )
        handler = InvocationCancelledHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        # Verify activity context (stored in AuditEvent, not structured_data)
        assert result.activity_id == "activity-789"
        assert result.resource_name == "approval_flow"

    def test_invocation_cancelled_not_found_no_activity_context(self) -> None:
        """InvocationCancelledEvent for NOT_FOUND result has no activity context."""
        invocation_id = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.NOT_FOUND,
            reason="Invocation not found",
            # No activity_id/activity_name when invocation doesn't exist
        )
        handler = InvocationCancelledHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.ERROR
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        # Verify no activity context (stored in AuditEvent, not structured_data)
        assert result.activity_id is None
        assert result.resource_name is None

    def test_resource_urn_format(self) -> None:
        """Resource URN follows RFC 8141 format."""
        invocation_id = uuid4()
        event = InvocationCancelledEvent(
            invocation_id=invocation_id,
            result=InvocationCancellationResult.SUCCESS,
            reason="URN test",
        )
        handler = InvocationCancelledHandler()
        result = handler.handle(event)

        # Verify URN format: urn:syntara:invocation:<uuid>
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        assert result.resource_urn.startswith("urn:syntara:invocation:")
