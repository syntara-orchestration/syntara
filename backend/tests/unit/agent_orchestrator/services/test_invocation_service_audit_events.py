"""Integration tests for audit event emission from invocations domain services.

These tests verify that InvocationService methods correctly dispatch domain events
which are then converted to AuditEvents by the registered handlers.
"""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models import Invocation, InvocationStatus
from syntara.agent_orchestrator.services.invocation_service import InvocationService
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.sanitization import REDACTED
from syntara.core.models import User
from syntara.files.models import FileMetadata

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent


class TestInvocationServiceCreateAuditEvents:
    """Tests for audit event emission from InvocationService.create_invocation()."""

    def setup_method(self) -> None:
        """Register invocations audit handlers before each test."""
        from syntara.invocations.audit.invocation_created import (
            InvocationCreatedEvent,
            InvocationCreatedHandler,
        )

        AuditEventDispatcher.register({InvocationCreatedEvent: InvocationCreatedHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_invocation_success_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful invocation creation should emit InvocationCreatedEvent."""
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_file_manager = Mock()
        mock_file_manager.validate_and_save_files = AsyncMock(return_value=[])

        service = InvocationService(
            session=mock_session,
            user=test_user,
            file_manager_factory=lambda: mock_file_manager,
        )

        # Act
        invocation = await service.create_invocation(
            prompt="Test prompt",
            session_id="session-123",
            project_id=uuid4(),
        )

        # Assert - verify audit event was emitted
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "invocation_created"
        assert event.event_category == EventCategory.USER_ACTION
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.invocations.create"
        assert event.event_message == "Invocation created for session session-123"
        assert event.resource_urn == f"urn:syntara:invocation:{invocation.id}"

        # Verify structured data
        assert event.structured_data.invocation_id == str(invocation.id)  # type: ignore[attr-defined]
        # session_id is redacted by PII sanitizer (contains "session" keyword)
        assert event.structured_data.session_id == REDACTED  # type: ignore[attr-defined]
        assert event.structured_data.file_ids == []  # type: ignore[attr-defined]
        assert event.structured_data.error_type is None
        assert event.structured_data.error_message is None

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_invocation_with_context_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Invocation with agent/model/metadata should include context in audit event."""
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_file_manager = Mock()
        mock_file_manager.validate_and_save_files = AsyncMock(return_value=[])

        service = InvocationService(
            session=mock_session,
            user=test_user,
            file_manager_factory=lambda: mock_file_manager,
        )

        # Act
        await service.create_invocation(
            prompt="Test prompt",
            session_id="session-456",
            project_id=uuid4(),
            context_data={
                "agent": "workflow-agent",
                "model": "gpt-4",
                "callback_url": "https://example.com/webhook",
                "metadata": {
                    "response_schema": {"type": "object", "properties": {}},
                },
            },
        )

        # Assert
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_status == EventStatus.SUCCESS
        assert event.structured_data.agent == "workflow-agent"  # type: ignore[attr-defined]
        assert event.structured_data.model == "gpt-4"  # type: ignore[attr-defined]

        # Verify sensitive fields excluded by audit_safe_metadata()
        data_dict = event.structured_data.model_dump()
        metadata = data_dict["metadata"]
        assert "response_schema" not in metadata

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_invocation_with_files_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Invocation with uploaded files should include file_ids in audit event."""
        # Arrange
        file_id_1 = uuid4()
        file_id_2 = uuid4()
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        mock_file_metadata = [
            FileMetadata(id=file_id_1, filename="file1.pdf", mime_type="application/pdf", size_bytes=1024),
            FileMetadata(id=file_id_2, filename="file2.txt", mime_type="text/plain", size_bytes=512),
        ]
        mock_file_manager = Mock()
        mock_file_manager.validate_and_save_files = AsyncMock(return_value=mock_file_metadata)

        service = InvocationService(
            session=mock_session,
            user=test_user,
            file_manager_factory=lambda: mock_file_manager,
        )

        mock_upload_file = Mock()
        mock_upload_file.filename = "test.pdf"

        # Act
        await service.create_invocation(
            prompt="Test prompt",
            session_id="session-789",
            project_id=uuid4(),
            files=[mock_upload_file],
        )

        # Assert
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_status == EventStatus.SUCCESS
        assert event.structured_data.file_ids == [str(file_id_1), str(file_id_2)]  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_invocation_db_error_emits_error_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Database error during invocation creation should emit error audit event before raising."""
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock(side_effect=Exception("DB Error"))
        mock_file_manager = Mock()
        mock_file_manager.validate_and_save_files = AsyncMock(return_value=[])

        service = InvocationService(
            session=mock_session,
            user=test_user,
            file_manager_factory=lambda: mock_file_manager,
        )

        # Act & Assert
        with pytest.raises(Exception, match="DB Error"):
            await service.create_invocation(
                prompt="Test prompt",
                session_id="session-error",
                project_id=uuid4(),
            )

        # Verify error audit event was emitted
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "invocation_created"
        assert event.event_category == EventCategory.SYSTEM_OPERATION
        assert event.event_severity == EventSeverity.ERROR
        assert event.event_status == EventStatus.ERROR
        assert event.event_message == "Invocation creation failed due to system error"
        assert event.structured_data.error_type == "Exception"
        assert event.structured_data.error_message is not None
        assert "Operational Logs" in event.structured_data.error_message


class TestInvocationServiceCancelAuditEvents:
    """Tests for audit event emission from InvocationService.cancel_invocation()."""

    def setup_method(self) -> None:
        """Register invocations audit handlers before each test."""
        from syntara.invocations.audit.invocation_cancelled import (
            InvocationCancelledEvent,
            InvocationCancelledHandler,
        )

        AuditEventDispatcher.register({InvocationCancelledEvent: InvocationCancelledHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_cancel_invocation_success_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful cancellation should emit InvocationCancelledEvent with SUCCESS result."""
        # Arrange
        invocation_id = uuid4()
        invocation = Invocation(
            id=invocation_id,
            prompt="Test prompt",
            created_by=uuid4(),
            session_id="session-123",
            status=InvocationStatus.RUNNING,
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.get = AsyncMock(return_value=invocation)
        mock_session.commit = AsyncMock()
        mock_file_manager = Mock()
        mock_file_manager.get_files_metadata = AsyncMock(return_value=[])

        service = InvocationService(
            session=mock_session,
            user=test_user,
            file_manager_factory=lambda: mock_file_manager,
        )

        # Act
        result = await service.cancel_invocation(invocation_id, reason="User requested")

        # Assert
        from syntara.agent_orchestrator.models.request import CancellationResult

        assert result == CancellationResult.SUCCESS
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "invocation_cancelled"
        assert event.event_category == EventCategory.USER_ACTION
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.invocations.cancel"
        assert event.event_message == "Invocation cancelled: User requested"
        assert event.resource_urn == f"urn:syntara:invocation:{invocation_id}"

        # Verify structured data
        assert event.structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]
        assert event.structured_data.cancellation_reason == "User requested"  # type: ignore[attr-defined]
        assert event.structured_data.current_status == InvocationStatus.CANCELLED  # type: ignore[attr-defined]
        assert event.structured_data.error_type is None
        assert event.structured_data.error_message is None

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_cancel_invocation_not_found_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Cancelling non-existent invocation should emit NOT_FOUND audit event."""
        # Arrange
        invocation_id = uuid4()
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.get = AsyncMock(return_value=None)

        service = InvocationService(
            session=mock_session,
            user=test_user,
        )

        # Act
        result = await service.cancel_invocation(invocation_id, reason="Test")

        # Assert
        from syntara.agent_orchestrator.models.request import CancellationResult

        assert result == CancellationResult.NOT_FOUND
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_severity == EventSeverity.WARNING
        assert event.event_status == EventStatus.ERROR
        assert event.event_message == "Invocation cancellation failed (not found)"
        assert event.structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_cancel_invocation_not_cancellable_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Cancelling completed invocation should emit NOT_CANCELLABLE audit event."""
        # Arrange
        invocation_id = uuid4()
        invocation = Invocation(
            id=invocation_id,
            prompt="Test prompt",
            created_by=uuid4(),
            session_id="session-123",
            status=InvocationStatus.COMPLETED,  # Already completed
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.get = AsyncMock(return_value=invocation)

        service = InvocationService(
            session=mock_session,
            user=test_user,
        )

        # Act
        result = await service.cancel_invocation(invocation_id, reason="Test")

        # Assert
        from syntara.agent_orchestrator.models.request import CancellationResult

        assert result == CancellationResult.NOT_CANCELLABLE
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_severity == EventSeverity.WARNING
        assert event.event_status == EventStatus.ERROR
        assert event.event_message == f"Invocation cancellation failed (status: {InvocationStatus.COMPLETED})"
        assert event.structured_data.current_status == InvocationStatus.COMPLETED  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_cancel_invocation_with_files_cleanup_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Cancelling invocation with files should include cleaned file_ids in audit event."""
        # Arrange
        invocation_id = uuid4()
        file_id_1 = uuid4()
        file_id_2 = uuid4()

        invocation = Invocation(
            id=invocation_id,
            prompt="Test prompt",
            created_by=uuid4(),
            session_id="session-123",
            status=InvocationStatus.RUNNING,
            context_data={"file_ids": [str(file_id_1), str(file_id_2)]},
        )

        mock_file_metadata = [
            FileMetadata(
                id=file_id_1,
                filename="file1.pdf",
                mime_type="application/pdf",
                size_bytes=1024,
                file_path="path/to/file1.pdf",
            ),
            FileMetadata(
                id=file_id_2,
                filename="file2.txt",
                mime_type="text/plain",
                size_bytes=512,
                file_path="path/to/file2.txt",
            ),
        ]

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.get = AsyncMock(return_value=invocation)
        mock_session.commit = AsyncMock()
        mock_retriever = AsyncMock()
        mock_retriever.delete_file = AsyncMock(return_value=True)
        mock_file_manager = Mock()
        mock_file_manager.get_files_metadata = AsyncMock(return_value=mock_file_metadata)
        mock_file_manager.get_retriever = Mock(return_value=mock_retriever)

        service = InvocationService(
            session=mock_session,
            user=test_user,
            file_manager_factory=lambda: mock_file_manager,
        )

        # Act
        await service.cancel_invocation(invocation_id, reason="Cleanup test")

        # Assert
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_status == EventStatus.SUCCESS
        # files_cleaned contains UUID strings (converted by Pydantic serialization)
        assert set(event.structured_data.files_cleaned) == {str(file_id_1), str(file_id_2)}  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_cancel_invocation_commit_error_emits_error_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Database error during cancellation should emit error audit event before raising."""
        # Arrange
        invocation_id = uuid4()
        invocation = Invocation(
            id=invocation_id,
            prompt="Test prompt",
            created_by=uuid4(),
            session_id="session-error",
            status=InvocationStatus.RUNNING,
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.get = AsyncMock(return_value=invocation)
        mock_session.commit = AsyncMock(side_effect=Exception("DB Error"))
        mock_file_manager = Mock()
        mock_file_manager.get_files_metadata = AsyncMock(return_value=[])

        service = InvocationService(
            session=mock_session,
            user=test_user,
            file_manager_factory=lambda: mock_file_manager,
        )

        # Act & Assert
        with pytest.raises(Exception, match="DB Error"):
            await service.cancel_invocation(invocation_id, reason="Test")

        # Verify error audit event was emitted
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "invocation_cancelled"
        # Note: Result is SUCCESS but error_type is set due to commit failure
        assert event.structured_data.error_type == "Exception"
