"""Unit tests for AAP job execution audit events, handlers, and dispatch helpers."""

# mypy: disable-error-code="attr-defined"

from unittest.mock import patch
from uuid import UUID, uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.core.models.principal import PrincipalType
from syntara.workflows.audit.aap_job_execution import (
    AAPJobCompletedEvent,
    AAPJobCompletedHandler,
    AAPJobFailedEvent,
    AAPJobFailedHandler,
    AAPJobLaunchedEvent,
    AAPJobLaunchedHandler,
    dispatch_audit_event,
    emit_completed,
    emit_failed,
    emit_launched,
    is_failure_status,
)

EXECUTION_ID = uuid4()
ACTOR_ID = uuid4()


class TestAAPJobLaunchedHandler:
    """Tests for AAPJobLaunchedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(AAPJobLaunchedHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        event = AAPJobLaunchedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_template_name="Deploy App",
            job_id=123,
            job_url="https://aap.example.com/execution/jobs/playbook/123/output",
            integration_id=uuid4(),
            base_url="https://aap.example.com",
            actor_id=ACTOR_ID,
            actor_username="testuser",
        )
        result = AAPJobLaunchedHandler().handle(event)

        assert result.event_category == EventCategory.WORKFLOW_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "aap_job_launched"
        assert result.source_component == "syntara.workflows"
        assert result.execution_id == EXECUTION_ID
        assert result.actor_id == ACTOR_ID
        assert result.actor_username == "testuser"
        assert "Deploy App" in result.event_message
        assert "123" in result.event_message

    def test_resource_urn_job_template(self) -> None:
        event = AAPJobLaunchedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_id=123,
            job_url="https://aap.example.com/execution/jobs/playbook/123/output",
            base_url="https://aap.example.com",
        )
        result = AAPJobLaunchedHandler().handle(event)
        assert result.resource_urn == "urn:syntara:aap:job:123"

    def test_resource_urn_workflow_job_template(self) -> None:
        event = AAPJobLaunchedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_workflow_job_template",
            job_template_id=42,
            job_id=456,
            job_url="https://aap.example.com/execution/jobs/workflow/456/output",
            base_url="https://aap.example.com",
        )
        result = AAPJobLaunchedHandler().handle(event)
        assert result.resource_urn == "urn:syntara:aap:workflow_job:456"

    def test_structured_data(self) -> None:
        integration_id = uuid4()
        event = AAPJobLaunchedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_template_name="Deploy App",
            job_id=123,
            job_url="https://aap.example.com/execution/jobs/playbook/123/output",
            integration_id=integration_id,
            base_url="https://aap.example.com",
        )
        result = AAPJobLaunchedHandler().handle(event)

        assert result.structured_data.data_type == "aap-job-launched"
        assert result.structured_data.job_template_id == 42
        assert result.structured_data.job_template_name == "Deploy App"
        assert result.structured_data.base_url == "https://aap.example.com"
        assert result.structured_data.integration_id == str(integration_id)

    def test_system_actor_when_no_actor_id(self) -> None:
        event = AAPJobLaunchedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_id=123,
            job_url="https://aap.example.com/execution/jobs/playbook/123/output",
            base_url="https://aap.example.com",
        )
        result = AAPJobLaunchedHandler().handle(event)
        assert result.actor_type == PrincipalType.SYSTEM


class TestAAPJobCompletedHandler:
    """Tests for AAPJobCompletedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(AAPJobCompletedHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        event = AAPJobCompletedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_id=123,
            job_url="https://aap.example.com/execution/jobs/playbook/123/output",
            job_status="successful",
            duration_ms=5000,
            artifacts={"changed": 5, "ok": 10},
            actor_id=ACTOR_ID,
            actor_username="testuser",
        )
        result = AAPJobCompletedHandler().handle(event)

        assert result.event_category == EventCategory.WORKFLOW_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "aap_job_completed"
        assert result.source_component == "syntara.workflows"
        assert result.execution_id == EXECUTION_ID
        assert "123" in result.event_message
        assert "successful" in result.event_message

    def test_structured_data(self) -> None:
        event = AAPJobCompletedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_id=123,
            job_url="https://aap.example.com/execution/jobs/playbook/123/output",
            job_status="successful",
            duration_ms=5000,
            artifacts={"changed": 5},
        )
        result = AAPJobCompletedHandler().handle(event)

        assert result.structured_data.data_type == "aap-job-completed"
        assert result.structured_data.job_status == "successful"
        assert result.structured_data.duration_ms == 5000
        assert result.structured_data.artifacts == {"changed": 5}

    def test_resource_urn(self) -> None:
        event = AAPJobCompletedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_workflow_job_template",
            job_template_id=42,
            job_id=789,
            job_url="https://aap.example.com/execution/jobs/workflow/789/output",
            job_status="successful",
        )
        result = AAPJobCompletedHandler().handle(event)
        assert result.resource_urn == "urn:syntara:aap:workflow_job:789"


class TestAAPJobFailedHandler:
    """Tests for AAPJobFailedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(AAPJobFailedHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        event = AAPJobFailedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_id=123,
            job_url="https://aap.example.com/execution/jobs/playbook/123/output",
            job_status="failed",
            duration_ms=3000,
            error_type="AAPJobExecutionError",
            error_message="Playbook failed on host web01",
            actor_id=ACTOR_ID,
            actor_username="testuser",
        )
        result = AAPJobFailedHandler().handle(event)

        assert result.event_category == EventCategory.WORKFLOW_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "aap_job_failed"
        assert result.source_component == "syntara.workflows"
        assert result.execution_id == EXECUTION_ID
        assert "123" in result.event_message
        assert "failed" in result.event_message

    def test_structured_data(self) -> None:
        event = AAPJobFailedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_id=123,
            job_url="https://aap.example.com/execution/jobs/playbook/123/output",
            job_status="error",
            error_type="AAPJobExecutionError",
            error_message="Connection timeout",
        )
        result = AAPJobFailedHandler().handle(event)

        assert result.structured_data.data_type == "aap-job-failed"
        assert result.structured_data.job_status == "error"
        assert result.structured_data.error_type == "AAPJobExecutionError"
        assert result.structured_data.error_message == "Connection timeout"

    def test_handles_none_job_id(self) -> None:
        """When launch itself fails, job_id is None."""
        event = AAPJobFailedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_status="error",
            error_type="ConnectionError",
            error_message="Could not connect to AAP",
        )
        result = AAPJobFailedHandler().handle(event)

        assert result.event_action == "aap_job_failed"
        assert result.resource_urn is None

    def test_resource_urn(self) -> None:
        event = AAPJobFailedEvent(
            execution_id=EXECUTION_ID,
            node_type="aap_job_template",
            job_template_id=42,
            job_id=123,
            job_url="https://aap.example.com/execution/jobs/playbook/123/output",
            job_status="canceled",
        )
        result = AAPJobFailedHandler().handle(event)
        assert result.resource_urn == "urn:syntara:aap:job:123"


_TEST_UUID = UUID("12345678-1234-5678-1234-567812345678")
_PATCH_TARGET = "syntara.workflows.audit.aap_job_execution.AuditEventDispatcher"


class TestIsFailureStatus:
    """Tests for is_failure_status helper."""

    def test_failed(self) -> None:
        assert is_failure_status("failed") is True
        assert is_failure_status("Failed") is True
        assert is_failure_status("FAILED") is True

    def test_error(self) -> None:
        assert is_failure_status("error") is True

    def test_canceled(self) -> None:
        assert is_failure_status("canceled") is True

    def test_successful_is_not_failure(self) -> None:
        assert is_failure_status("successful") is False

    def test_non_string(self) -> None:
        assert is_failure_status(None) is False
        assert is_failure_status(123) is False


class TestDispatchAuditEvent:
    """Tests for dispatch_audit_event helper."""

    def test_dispatches_event(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            dispatch_audit_event("test-event")
            mock.dispatch.assert_called_once_with("test-event")

    def test_swallows_exceptions(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            mock.dispatch.side_effect = RuntimeError("boom")
            dispatch_audit_event("test-event")


class TestEmitLaunched:
    """Tests for emit_launched."""

    def test_dispatches_when_ids_present(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_launched(
                _TEST_UUID, 42, job_id=100, job_url="http://url", base_url="http://base", node_type="aap_job_template"
            )
            mock.dispatch.assert_called_once()
            event = mock.dispatch.call_args[0][0]
            assert isinstance(event, AAPJobLaunchedEvent)
            assert event.node_type == "aap_job_template"

    def test_skips_when_exec_uuid_none(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_launched(
                None, 42, job_id=100, job_url="http://url", base_url="http://base", node_type="aap_job_template"
            )
            mock.dispatch.assert_not_called()

    def test_skips_when_template_id_none(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_launched(
                _TEST_UUID, None, job_id=100, job_url="http://url", base_url="http://base", node_type="aap_job_template"
            )
            mock.dispatch.assert_not_called()

    def test_passes_job_template_name(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_launched(
                _TEST_UUID,
                42,
                job_id=100,
                job_url="http://url",
                base_url="http://base",
                node_type="x",
                job_template_name="my-template",
            )
            event = mock.dispatch.call_args[0][0]
            assert event.job_template_name == "my-template"

    def test_passes_actor_id(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_launched(
                _TEST_UUID,
                42,
                job_id=100,
                job_url="http://url",
                base_url="http://base",
                node_type="aap_job_template",
                actor_id=ACTOR_ID,
            )
            event = mock.dispatch.call_args[0][0]
            assert event.actor_id == ACTOR_ID


class TestEmitCompleted:
    """Tests for emit_completed."""

    def test_dispatches_when_ids_present(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_completed(
                _TEST_UUID,
                42,
                job_id=100,
                job_url="http://url",
                final_status="successful",
                duration_ms=5000,
                artifacts={"ok": 1},
                node_type="aap_job_template",
            )
            mock.dispatch.assert_called_once()
            event = mock.dispatch.call_args[0][0]
            assert isinstance(event, AAPJobCompletedEvent)

    def test_skips_when_none(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_completed(
                None,
                42,
                job_id=100,
                job_url="http://url",
                final_status="successful",
                duration_ms=5000,
                artifacts=None,
                node_type="aap_job_template",
            )
            mock.dispatch.assert_not_called()

    def test_passes_actor_id(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_completed(
                _TEST_UUID,
                42,
                job_id=100,
                job_url="http://url",
                final_status="successful",
                duration_ms=5000,
                artifacts=None,
                node_type="aap_job_template",
                actor_id=ACTOR_ID,
            )
            event = mock.dispatch.call_args[0][0]
            assert event.actor_id == ACTOR_ID


class TestEmitFailed:
    """Tests for emit_failed."""

    def test_dispatches_when_ids_present(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_failed(_TEST_UUID, 42, job_status="failed", duration_ms=3000, node_type="aap_job_template", job_id=100)
            mock.dispatch.assert_called_once()
            event = mock.dispatch.call_args[0][0]
            assert isinstance(event, AAPJobFailedEvent)

    def test_skips_when_none(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_failed(None, None, job_status="failed", duration_ms=3000, node_type="aap_job_template")
            mock.dispatch.assert_not_called()

    def test_passes_error_details(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_failed(
                _TEST_UUID,
                42,
                job_status="error",
                duration_ms=1000,
                node_type="aap_job_template",
                error_type="RuntimeError",
                error_message="boom",
            )
            event = mock.dispatch.call_args[0][0]
            assert event.error_type == "RuntimeError"
            assert event.error_message == "boom"

    def test_passes_actor_id(self) -> None:
        with patch(_PATCH_TARGET) as mock:
            emit_failed(
                _TEST_UUID,
                42,
                job_status="failed",
                duration_ms=3000,
                node_type="aap_job_template",
                job_id=100,
                actor_id=ACTOR_ID,
            )
            event = mock.dispatch.call_args[0][0]
            assert event.actor_id == ACTOR_ID
