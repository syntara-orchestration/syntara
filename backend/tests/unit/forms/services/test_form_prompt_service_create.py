"""Unit tests for FormPromptService.create method.

Tests verify form prompt creation logic including validation,
duplicate detection, and database operations.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.forms.exceptions import (
    FormPromptAlreadyRequestedError,
    FormPromptExpiredError,
    FormPromptNotPendingError,
)
from syntara.forms.models.api_models import FormPromptCreateRequest, FormPromptStatus, FormPromptSummary
from syntara.forms.models.form_fields import FormDefinition
from syntara.forms.models.form_prompt import FormPrompt
from syntara.forms.services.form_prompt_service import FormPromptService

# Minimal valid form definition for tests
_MINIMAL_FORM_DEFINITION = {
    "fields": [{"value_name": "field1", "type": "text", "label": "Test Field", "required": False}]
}
_TEST_PROJECT_ID = uuid4()


@pytest.fixture(autouse=True)
def mock_audit_dispatcher(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Keep service unit tests focused on dispatch calls, not outbox side effects."""
    dispatcher = Mock()
    monkeypatch.setattr("syntara.forms.services.form_prompt_service.AuditEventDispatcher.dispatch", dispatcher)
    return dispatcher


def _make_service(*, raise_integrity_error: bool = False) -> tuple[FormPromptService, Mock]:
    """Build FormPromptService with mocked session."""
    session = Mock(spec=AsyncSession)

    session.add = Mock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    session.get = AsyncMock(return_value=SimpleNamespace(project_id=_TEST_PROJECT_ID))

    if raise_integrity_error:
        # Prompt creation flushes before dispatch, so an immediate uniqueness
        # constraint violation is raised here before the audit event is staged.
        orig_error = Exception('duplicate key value violates unique constraint "uix_execution_prompt_node_path"')
        session.flush = AsyncMock(
            side_effect=IntegrityError(
                'duplicate key value violates unique constraint "uix_execution_prompt_node_path"',
                params=None,
                orig=orig_error,
            )
        )
    session.commit = AsyncMock()

    # Create mock user for BaseService
    user = Mock()
    user.id = uuid4()

    svc = FormPromptService(session=session, user=user)
    return svc, session


def _mock_execution_project(session: Mock, project_id: UUID) -> None:
    """Configure the mocked execution to match a create request's project."""
    execution = Mock()
    execution.project_id = project_id
    execution.workflow_id = uuid4()
    execution.created_by = uuid4()
    session.get = AsyncMock(return_value=execution)


def _duplicate_request() -> FormPromptCreateRequest:
    """Create request used by the duplicate-handling tests."""
    return FormPromptCreateRequest(
        execution_id=uuid4(),
        project_id=_TEST_PROJECT_ID,
        prompt_node_id="form1",
        name="Form",
        form_definition=_MINIMAL_FORM_DEFINITION,
        loop_iteration_path=[],
        temporal_activity_id="form1",
    )


def _existing_prompt(
    request: FormPromptCreateRequest,
    *,
    status: FormPromptStatus = FormPromptStatus.PENDING,
    temporal_activity_id: str | None = None,
) -> FormPrompt:
    """Build the already-committed prompt that a duplicate create collides with."""
    return FormPrompt(
        id=uuid4(),
        execution_id=request.execution_id,
        project_id=request.project_id,
        prompt_node_id=request.prompt_node_id,
        name=request.name,
        form_definition=request.form_definition,
        loop_iteration_path=request.loop_iteration_path,
        temporal_activity_id=temporal_activity_id or request.temporal_activity_id,
        status=status,
    )


def _mock_existing_prompt(session: Mock, existing: FormPrompt | None) -> None:
    """Make the post-rollback duplicate lookup return ``existing``."""
    session.exec = AsyncMock(return_value=Mock(first=Mock(return_value=existing)))


class TestFormPromptServiceCreate:
    """Test FormPromptService.create method."""

    @pytest.mark.asyncio
    async def test_success_returns_form_prompt(self) -> None:
        """Successful creation returns FormPrompt with correct fields."""
        service, _session = _make_service()

        exec_id = uuid4()
        proj_id = _TEST_PROJECT_ID
        request = FormPromptCreateRequest(
            execution_id=exec_id,
            project_id=proj_id,
            prompt_node_id="form1",
            name="Test Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            temporal_activity_id="form1",
        )

        _mock_execution_project(_session, proj_id)
        result = await service.create(request)

        assert result.execution_id == exec_id
        assert result.project_id == proj_id
        assert result.prompt_node_id == "form1"
        assert result.name == "Test Form"
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_success_stages_created_event_in_transaction(self, mock_audit_dispatcher: Mock) -> None:
        """Creation audit data is staged with the prompt in the same transaction."""
        service, session = _make_service()
        workflow_id = uuid4()
        initiated_by = uuid4()
        execution = Mock(project_id=_TEST_PROJECT_ID, workflow_id=workflow_id, created_by=initiated_by)
        session.get = AsyncMock(return_value=execution)
        request = FormPromptCreateRequest(
            execution_id=uuid4(),
            project_id=_TEST_PROJECT_ID,
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            temporal_activity_id="form1",
        )
        order: list[str] = []

        async def commit() -> None:
            order.append("commit")

        session.commit.side_effect = commit
        mock_audit_dispatcher.side_effect = lambda _event, **_kwargs: order.append("dispatch")

        await service.create(request)

        mock_audit_dispatcher.assert_called_once()
        event = mock_audit_dispatcher.call_args.args[0]
        assert event.prompt_id == session.add.call_args.args[0].id
        assert event.workflow_id == workflow_id
        assert event.execution_id == request.execution_id
        assert event.prompt_node_id == "form1"
        assert event.initiated_by == initiated_by
        assert event.created_at is not None
        assert mock_audit_dispatcher.call_args.kwargs["session"] is session
        assert order == ["dispatch", "commit"]

    @pytest.mark.asyncio
    async def test_success_adds_to_session(self) -> None:
        """Session.add is called with the new FormPrompt."""
        service, session = _make_service()

        request = FormPromptCreateRequest(
            execution_id=uuid4(),
            project_id=_TEST_PROJECT_ID,
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            temporal_activity_id="form1",
        )

        _mock_execution_project(session, request.project_id)
        await service.create(request)

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, FormPrompt)

    @pytest.mark.asyncio
    async def test_duplicate_without_existing_row_raises_already_requested(self, mock_audit_dispatcher: Mock) -> None:
        """A collision whose row cannot be found (e.g. deleted concurrently) still raises 409."""
        service, session = _make_service(raise_integrity_error=True)
        request = _duplicate_request()
        _mock_execution_project(session, request.project_id)
        _mock_existing_prompt(session, None)

        with pytest.raises(FormPromptAlreadyRequestedError, match="already exists"):
            await service.create(request)

        session.rollback.assert_awaited_once()
        mock_audit_dispatcher.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_for_different_activity_raises_already_requested(self, mock_audit_dispatcher: Mock) -> None:
        """A pending prompt owned by a different Temporal activity is not a replay."""
        service, session = _make_service(raise_integrity_error=True)
        request = _duplicate_request()
        _mock_execution_project(session, request.project_id)
        _mock_existing_prompt(session, _existing_prompt(request, temporal_activity_id="some_other_activity"))

        with pytest.raises(FormPromptAlreadyRequestedError, match="already exists"):
            await service.create(request)

        mock_audit_dispatcher.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_for_pending_prompt_of_same_activity_is_idempotent(
        self, mock_audit_dispatcher: Mock
    ) -> None:
        """Retry returns original content and responders without repeating side effects."""
        service, session = _make_service(raise_integrity_error=True)
        original_request = _duplicate_request()
        original_request.name = "Original form"
        original_request.message = "Original guidance"
        original_request.timeout_at = datetime.now(UTC) + timedelta(hours=1)
        original_request.form_definition = FormDefinition.model_validate(
            {"fields": [{"value_name": "original", "type": "text", "label": "Original label", "required": False}]}
        )
        original_request.submit_label = "Original submit"
        original_request.success_message = "Original success"
        retry_request = original_request.model_copy(
            update={
                "name": "Changed form",
                "message": "Changed guidance",
                "timeout_at": datetime.now(UTC) + timedelta(hours=2),
                "form_definition": {
                    "fields": [{"value_name": "changed", "type": "text", "label": "Changed label", "required": True}]
                },
                "submit_label": "Changed submit",
                "success_message": "Changed success",
                "responder_user_ids": [uuid4()],
                "responder_group_ids": [uuid4()],
            }
        )
        _mock_execution_project(session, retry_request.project_id)
        existing = _existing_prompt(original_request)
        existing.message = original_request.message
        existing.timeout_at = original_request.timeout_at
        existing.submit_label = original_request.submit_label
        existing.success_message = original_request.success_message
        _mock_existing_prompt(session, existing)
        original_summary = FormPromptSummary.model_validate(existing)

        result = await service.create(retry_request)

        assert result == original_summary
        assert result.name == "Original form"
        assert result.status == FormPromptStatus.PENDING
        assert result.temporal_activity_id == original_request.temporal_activity_id
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        mock_audit_dispatcher.assert_not_called()
        session.add.assert_called_once()
        assert isinstance(session.add.call_args.args[0], FormPrompt)  # no responder rows staged on replay

    @pytest.mark.asyncio
    async def test_duplicate_for_pending_prompt_past_deadline_raises_expired(self, mock_audit_dispatcher: Mock) -> None:
        """A pending row past its response deadline cannot be reused for a retry."""
        service, session = _make_service(raise_integrity_error=True)
        request = _duplicate_request()
        _mock_execution_project(session, request.project_id)
        existing = _existing_prompt(request)
        existing.timeout_at = datetime.now(UTC) - timedelta(seconds=1)
        _mock_existing_prompt(session, existing)

        with pytest.raises(FormPromptExpiredError) as exc_info:
            await service.create(request)

        assert exc_info.value.form_prompt_id == existing.id
        assert exc_info.value.timeout_at == existing.timeout_at
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        mock_audit_dispatcher.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "terminal_status",
        [FormPromptStatus.SUBMITTED, FormPromptStatus.EXPIRED, FormPromptStatus.CANCELLED],
    )
    async def test_duplicate_for_non_pending_prompt_raises_not_pending(
        self, terminal_status: FormPromptStatus, mock_audit_dispatcher: Mock
    ) -> None:
        """A retry cannot resume a prompt that was already submitted, expired or cancelled."""
        service, session = _make_service(raise_integrity_error=True)
        request = _duplicate_request()
        _mock_execution_project(session, request.project_id)
        existing = _existing_prompt(request, status=terminal_status)
        _mock_existing_prompt(session, existing)

        with pytest.raises(FormPromptNotPendingError) as exc_info:
            await service.create(request)

        assert exc_info.value.form_prompt_id == existing.id
        assert exc_info.value.current_status == terminal_status
        mock_audit_dispatcher.assert_not_called()

    @pytest.mark.asyncio
    async def test_temporal_activity_id_uses_provided_value(self) -> None:
        """temporal_activity_id is set from request when provided."""
        service, session = _make_service()

        request = FormPromptCreateRequest(
            execution_id=uuid4(),
            project_id=_TEST_PROJECT_ID,
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            temporal_activity_id="form1_iter_0",
        )

        _mock_execution_project(session, request.project_id)
        await service.create(request)

        added = session.add.call_args[0][0]
        assert added.temporal_activity_id == "form1_iter_0"

    @pytest.mark.asyncio
    async def test_responder_users_creates_junction_rows(self) -> None:
        """responder_user_ids creates FormPromptResponderUser junctions."""
        service, session = _make_service()

        user1 = uuid4()
        user2 = uuid4()
        request = FormPromptCreateRequest(
            execution_id=uuid4(),
            project_id=_TEST_PROJECT_ID,
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            responder_user_ids=[user1, user2],
            temporal_activity_id="form1",
        )

        _mock_execution_project(session, request.project_id)
        await service.create(request)

        # Should add FormPrompt + 2 responder junctions
        assert session.add.call_count == 3

    @pytest.mark.asyncio
    async def test_responder_groups_creates_junction_rows(self) -> None:
        """responder_group_ids creates FormPromptResponderGroup junctions."""
        service, session = _make_service()

        group1 = uuid4()
        request = FormPromptCreateRequest(
            execution_id=uuid4(),
            project_id=_TEST_PROJECT_ID,
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            responder_group_ids=[group1],
            temporal_activity_id="form1",
        )

        _mock_execution_project(session, request.project_id)
        await service.create(request)

        # Should add FormPrompt + 1 group junction
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_loop_iteration_path_stored_correctly(self) -> None:
        """loop_iteration_path is stored in the FormPrompt."""
        service, session = _make_service()

        request = FormPromptCreateRequest(
            execution_id=uuid4(),
            project_id=_TEST_PROJECT_ID,
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            loop_iteration_path=[0, 1],
            temporal_activity_id="form1",
        )

        _mock_execution_project(session, request.project_id)
        await service.create(request)

        added = session.add.call_args[0][0]
        assert added.loop_iteration_path == [0, 1]
