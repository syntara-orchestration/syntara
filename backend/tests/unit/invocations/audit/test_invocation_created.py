"""Unit tests for InvocationCreatedEvent and InvocationCreatedHandler."""

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.invocations.audit.invocation_created import InvocationCreatedEvent, InvocationCreatedHandler


class TestInvocationCreatedEvent:
    """Tests for InvocationCreatedEvent dataclass."""

    def test_minimal_construction_defaults(self) -> None:
        """InvocationCreatedEvent can be constructed with minimal required fields; defaults apply."""
        invocation_id = uuid4()
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-123",
        )
        assert event.invocation_id == invocation_id
        assert event.session_id == "session-123"
        assert event.file_ids == []
        assert event.agent is None
        assert event.model is None
        assert event.metadata is None
        assert event.error_type is None

    def test_enrichment_with_full_context(self) -> None:
        """InvocationCreatedEvent can be enriched with full context data."""
        invocation_id = uuid4()
        file_id_1 = str(uuid4())
        file_id_2 = str(uuid4())
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-456",
            file_ids=[file_id_1, file_id_2],
            agent="workflow-agent",
            model="gpt-4",
            metadata={"priority": "high"},
        )
        assert event.file_ids == [file_id_1, file_id_2]
        assert event.agent == "workflow-agent"
        assert event.model == "gpt-4"
        assert event.metadata == {"priority": "high"}

    def test_error_type_can_be_set(self) -> None:
        """error_type can be set to indicate failure."""
        invocation_id = uuid4()
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-789",
            error_type="SQLAlchemyError",
        )
        assert event.error_type == "SQLAlchemyError"


class TestInvocationCreatedHandler:
    """Tests for InvocationCreatedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """InvocationCreatedHandler is a subclass of AuditEventHandler."""
        assert issubclass(InvocationCreatedHandler, AuditEventHandler)

    def test_successful_creation(self) -> None:
        """Successful creation produces USER_ACTION / INFO / SUCCESS / 'invocation_created' event."""
        invocation_id = uuid4()
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-123",
        )
        handler = InvocationCreatedHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "invocation_created"
        assert result.source_component == "syntara.invocations.create"
        assert result.event_message == "Invocation created for session session-123"
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        # Without activity context, resource_name should be None
        assert result.resource_name is None

    def test_successful_creation_with_files_and_context(self) -> None:
        """Successful creation with files and context captures all fields in structured_data."""
        invocation_id = uuid4()
        file_id_1 = str(uuid4())
        file_id_2 = str(uuid4())
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-456",
            file_ids=[file_id_1, file_id_2],
            agent="workflow-agent",
            model="gpt-4",
            metadata={"priority": "high"},
        )
        handler = InvocationCreatedHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "invocation-created-context"
        assert result.structured_data.invocation_id == invocation_id  # type: ignore[attr-defined]
        assert result.structured_data.session_id == "session-456"  # type: ignore[attr-defined]
        assert result.structured_data.file_ids == [file_id_1, file_id_2]  # type: ignore[attr-defined]
        assert result.structured_data.agent == "workflow-agent"  # type: ignore[attr-defined]
        assert result.structured_data.model == "gpt-4"  # type: ignore[attr-defined]
        # Access extra fields via model_dump() to avoid Pydantic metadata field collision
        data_dict = result.structured_data.model_dump()
        assert data_dict["metadata"] == {"priority": "high"}
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_failed_creation_technical_error(self) -> None:
        """Failed creation with technical error produces SYSTEM_OPERATION / ERROR / ERROR event."""
        invocation_id = uuid4()
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-789",
            error_type="SQLAlchemyError",
        )
        handler = InvocationCreatedHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SYSTEM_OPERATION
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "invocation_created"
        assert result.event_message == "Invocation creation failed due to system error"
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "SQLAlchemyError"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    def test_invocation_created_includes_activity_context(self) -> None:
        """InvocationCreatedEvent includes activity_id and activity_name from workflow context."""
        invocation_id = uuid4()
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-workflow",
            activity_id="activity-456",
            activity_name="agentic_v2",
        )
        handler = InvocationCreatedHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        # Verify activity context (stored in AuditEvent, not structured_data)
        assert result.activity_id == "activity-456"
        assert result.resource_name == "agentic_v2"

    def test_invocation_created_without_activity_context(self) -> None:
        """InvocationCreatedEvent without workflow context has no activity fields."""
        invocation_id = uuid4()
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-no-workflow",
        )
        handler = InvocationCreatedHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        # Verify no activity context (stored in AuditEvent, not structured_data)
        assert result.activity_id is None
        assert result.resource_name is None

    def test_resource_urn_format(self) -> None:
        """Resource URN follows RFC 8141 format."""
        invocation_id = uuid4()
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-urn",
        )
        handler = InvocationCreatedHandler()
        result = handler.handle(event)

        # Verify URN format: urn:syntara:invocation:<uuid>
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"
        assert result.resource_urn.startswith("urn:syntara:invocation:")

    def test_sensitive_metadata_fields_excluded(self) -> None:
        """Sensitive fields are excluded via audit_safe_metadata() at the emit site."""
        from syntara.agent_orchestrator.models.context_data import InvocationContextData

        invocation_id = uuid4()
        ctx = InvocationContextData.model_validate(
            {
                "metadata": {
                    "credential_id": "secret-cred",
                    "response_schema": {"type": "object", "properties": {}},
                },
            }
        )
        event = InvocationCreatedEvent(
            invocation_id=invocation_id,
            session_id="session-sensitive",
            metadata=ctx.audit_safe_metadata(),
        )
        handler = InvocationCreatedHandler()
        result = handler.handle(event)

        data_dict = result.structured_data.model_dump()
        metadata = data_dict["metadata"]

        # Sensitive fields must be removed.
        # Note: credential_id and response_schema are excluded by
        # InvocationMetadata.audit_safe_dump() because they are typed as
        # SecretStr / OpaqueResponseSchema.  callback_url lives on
        # InvocationContextData (not InvocationMetadata), so it can never
        # appear in audit_safe_metadata() output.  These asserts guard
        # against regressions in the typed model rather than in the handler.
        assert "credential_id" not in metadata
        assert "response_schema" not in metadata
        assert "callback_url" not in metadata
