"""Unit tests for InternalServiceDeniedEvent/Handler."""

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.authz.audit.internal_service_denied import (
    InternalServiceDeniedEvent,
    InternalServiceDeniedHandler,
)


class TestInternalServiceDeniedHandler:
    """Tests for InternalServiceDeniedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(InternalServiceDeniedHandler, AuditEventHandler)

    def test_maps_event_to_security_audit_event(self) -> None:
        event = InternalServiceDeniedEvent(
            reason="authorization_header_present",
            path="/api/v1/form_prompts",
            method="POST",
            cert_cn="worker.ao.svc",
        )

        result = InternalServiceDeniedHandler().handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "internal_service_denied"
        assert result.source_component == "syntara.authz"
        assert "POST /api/v1/form_prompts" in result.event_message
        assert "authorization_header_present" in result.event_message
        data = result.structured_data.model_dump()
        assert data["data_type"] == "internal-service-denied"
        assert data["reason"] == "authorization_header_present"
        assert data["path"] == "/api/v1/form_prompts"
        assert data["method"] == "POST"
        assert data["cert_cn"] == "worker.ao.svc"
