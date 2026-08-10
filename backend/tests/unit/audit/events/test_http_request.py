"""Unit tests for HTTPRequestEvent and HTTPRequestHandler."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.emitter import AuditActorContext
from syntara.audit.events.http_request import HTTPRequestEvent, HTTPRequestHandler
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType


class TestHTTPRequestHandler:
    """Tests for HTTPRequestHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """HTTPRequestHandler is a subclass of AuditEventHandler."""
        handler = HTTPRequestHandler()
        assert isinstance(handler, AuditEventHandler)

    def test_successful_request_200(self) -> None:
        """Successful 2xx request produces INFO severity and SUCCESS status."""
        user_id = uuid4()
        event = HTTPRequestEvent(
            method="GET",
            path="/api/v1/workflows",
            status_code=200,
            actor_context=AuditActorContext(
                actor_id=user_id, actor_username="test-user", actor_type=PrincipalType.USER
            ),
        )

        handler = HTTPRequestHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "request_completed"
        assert result.event_message == "Request completed: GET /api/v1/workflows 200"
        assert result.actor_id == user_id
        assert result.actor_type == PrincipalType.USER
        assert result.source_component == "syntara.audit.middleware"

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "request_completed"
        assert result.structured_data.method == "GET"
        assert result.structured_data.path == "/api/v1/workflows"
        assert result.structured_data.status_code == 200

    def test_client_error_400(self) -> None:
        """Client error 4xx request produces WARNING severity and ERROR status."""
        event = HTTPRequestEvent(
            method="POST",
            path="/api/v1/workflows",
            status_code=400,
            actor_context=AuditActorContext(),
        )

        handler = HTTPRequestHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.status_code == 400

    def test_not_found_404(self) -> None:
        """Not found 404 request produces WARNING severity and ERROR status."""
        event = HTTPRequestEvent(
            method="GET",
            path="/api/v1/nonexistent",
            status_code=404,
            actor_context=AuditActorContext(),
        )

        handler = HTTPRequestHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR

    def test_server_error_500(self) -> None:
        """Server error 5xx request produces ERROR severity and ERROR status."""
        event = HTTPRequestEvent(
            method="GET",
            path="/api/v1/workflows",
            status_code=500,
            actor_context=AuditActorContext(),
        )

        handler = HTTPRequestHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.status_code == 500

    def test_includes_query_params(self) -> None:
        """Query parameters are included in structured data."""
        event = HTTPRequestEvent(
            method="GET",
            path="/api/v1/workflows",
            status_code=200,
            query_params={"filter": "active", "limit": "10"},
            actor_context=AuditActorContext(),
        )

        handler = HTTPRequestHandler()
        result = handler.handle(event)

        assert result.structured_data.query_params == {"filter": "active", "limit": "10"}

    def test_includes_context_ids(self) -> None:
        """Workflow, execution, and activity IDs are preserved in the audit event."""
        workflow_id = uuid4()
        execution_id = uuid4()
        activity_id = "task_1"

        event = HTTPRequestEvent(
            method="GET",
            path=f"/api/v1/workflows/{workflow_id}/executions/{execution_id}",
            status_code=200,
            actor_context=AuditActorContext(),
            workflow_id=workflow_id,
            execution_id=execution_id,
            activity_id=activity_id,
        )

        handler = HTTPRequestHandler()
        result = handler.handle(event)

        assert result.workflow_id == workflow_id
        assert result.execution_id == execution_id
        assert result.activity_id == activity_id

    def test_custom_source_component(self) -> None:
        """Custom source component is preserved."""
        event = HTTPRequestEvent(
            method="GET",
            path="/api/v1/workflows",
            status_code=200,
            source_component="syntara.workflows.router",
            actor_context=AuditActorContext(),
        )

        handler = HTTPRequestHandler()
        result = handler.handle(event)

        assert result.source_component == "syntara.workflows.router"

    def test_unauthenticated_request(self) -> None:
        """Unauthenticated request has no actor."""
        event = HTTPRequestEvent(
            method="GET",
            path="/health",
            status_code=200,
            actor_context=AuditActorContext(),
        )

        handler = HTTPRequestHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_type is None
