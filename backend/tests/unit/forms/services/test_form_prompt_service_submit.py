"""Unit tests for FormPromptService.submit method.

Tests verify form submission logic including validation, database updates,
signal delivery, and telemetry emission.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.forms.exceptions import (
    FormPromptAlreadyRespondedError,
    FormPromptCancelledError,
    FormPromptExpiredError,
    FormPromptNotFoundError,
)
from syntara.forms.models.api_models import FormPromptStatus
from syntara.forms.models.form_prompt import FormPrompt
from syntara.forms.services.form_prompt_service import FormPromptService

# Minimal valid form definition for tests
_MINIMAL_FORM_DEFINITION = {
    "fields": [{"value_name": "field1", "type": "text", "label": "Test Field", "required": True}]
}


def _make_service_with_user(*, prompt: FormPrompt | None = None) -> tuple[FormPromptService, Mock, Mock]:
    """Build FormPromptService with mocked session and user."""
    session = Mock(spec=AsyncSession)
    user = Mock()
    user.id = uuid4()
    user.username = "testuser"

    # Mock session.get for prompt lookups
    session.get = AsyncMock(return_value=prompt)

    # Mock session.execute for UPDATE statement
    mock_result = Mock()
    mock_result.rowcount = 1 if prompt and prompt.status == FormPromptStatus.PENDING else 0
    session.execute = AsyncMock(return_value=mock_result)

    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    svc = FormPromptService(session=session, user=user)
    return svc, session, user


class TestFormPromptServiceSubmit:
    """Test FormPromptService.submit method."""

    @pytest.mark.asyncio
    async def test_submit_success_updates_status(self) -> None:
        """Successful submission updates status to SUBMITTED."""
        prompt_id = uuid4()
        prompt = Mock(spec=FormPrompt)
        prompt.id = prompt_id
        prompt.status = FormPromptStatus.PENDING
        prompt.timeout_at = None
        prompt.form_definition = _MINIMAL_FORM_DEFINITION
        prompt.execution_id = uuid4()
        prompt.prompt_node_id = "form1"
        prompt.temporal_activity_id = "form1"
        prompt.created_at = datetime.now(UTC) - timedelta(seconds=30)

        service, session, _user = _make_service_with_user(prompt=prompt)

        submitted_data = {"field1": "test value"}

        with (
            patch("syntara.forms.services.form_prompt_service.validate_form_submission") as mock_validate,
            patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as mock_client_cls,
            patch("syntara.forms.services.form_prompt_service.AuditEventDispatcher") as mock_dispatcher,
        ):
            mock_validate.return_value = submitted_data
            mock_client = Mock()
            mock_client.send_form_signal = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await service.submit(prompt_id, submitted_data)

            # Should commit the transaction
            session.commit.assert_called_once()

            # Should refresh the prompt
            session.refresh.assert_called_once()

            # Should dispatch audit event
            mock_dispatcher.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_sends_workflow_signal(self) -> None:
        """Successful submission sends signal to workflow engine."""
        prompt_id = uuid4()
        execution_id = uuid4()
        prompt = Mock(spec=FormPrompt)
        prompt.id = prompt_id
        prompt.status = FormPromptStatus.PENDING
        prompt.timeout_at = None
        prompt.form_definition = _MINIMAL_FORM_DEFINITION
        prompt.execution_id = execution_id
        prompt.prompt_node_id = "form1"
        prompt.temporal_activity_id = "form1_iter_0"
        prompt.created_at = datetime.now(UTC) - timedelta(seconds=30)

        service, _session, user = _make_service_with_user(prompt=prompt)

        submitted_data = {"field1": "test value"}

        with (
            patch("syntara.forms.services.form_prompt_service.validate_form_submission") as mock_validate,
            patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as mock_client_cls,
            patch("syntara.forms.services.form_prompt_service.AuditEventDispatcher"),
        ):
            mock_validate.return_value = submitted_data
            mock_client = Mock()
            mock_client.send_form_signal = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await service.submit(prompt_id, submitted_data)

            # Should send signal with correct parameters
            mock_client.send_form_signal.assert_called_once()
            call_kwargs = mock_client.send_form_signal.call_args.kwargs
            assert call_kwargs["execution_id"] == execution_id
            assert call_kwargs["form_prompt_id"] == "form1"
            assert call_kwargs["temporal_activity_id"] == "form1_iter_0"
            assert call_kwargs["form_response"]["outcome"] == "submitted"
            assert call_kwargs["form_response"]["response_data"] == submitted_data
            assert call_kwargs["form_response"]["responded_by"] == user.username

    @pytest.mark.asyncio
    async def test_submit_emits_telemetry_with_pause_duration(self) -> None:
        """Submission emits audit event with pause duration."""
        prompt_id = uuid4()
        created_at = datetime.now(UTC) - timedelta(seconds=45)
        prompt = Mock(spec=FormPrompt)
        prompt.id = prompt_id
        prompt.status = FormPromptStatus.PENDING
        prompt.timeout_at = None
        prompt.form_definition = _MINIMAL_FORM_DEFINITION
        prompt.execution_id = uuid4()
        prompt.prompt_node_id = "form1"
        prompt.temporal_activity_id = "form1"
        prompt.created_at = created_at

        service, _session, _user = _make_service_with_user(prompt=prompt)

        submitted_data = {"field1": "test value"}

        with (
            patch("syntara.forms.services.form_prompt_service.validate_form_submission") as mock_validate,
            patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as mock_client_cls,
            patch("syntara.forms.services.form_prompt_service.AuditEventDispatcher") as mock_dispatcher,
        ):
            mock_validate.return_value = submitted_data
            mock_client = Mock()
            mock_client.send_form_signal = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await service.submit(prompt_id, submitted_data)

            # Should dispatch audit event with wait time
            mock_dispatcher.dispatch.assert_called_once()
            event = mock_dispatcher.dispatch.call_args.args[0]
            assert event.wait_time_ms >= 45000  # At least 45 seconds
            assert event.field_count == 1
            assert event.outcome == "submitted"

    @pytest.mark.asyncio
    async def test_submit_signal_failure_still_commits(self) -> None:
        """Signal failure doesn't prevent database commit (graceful degradation)."""
        prompt_id = uuid4()
        prompt = Mock(spec=FormPrompt)
        prompt.id = prompt_id
        prompt.status = FormPromptStatus.PENDING
        prompt.timeout_at = None
        prompt.form_definition = _MINIMAL_FORM_DEFINITION
        prompt.execution_id = uuid4()
        prompt.prompt_node_id = "form1"
        prompt.temporal_activity_id = "form1"
        prompt.created_at = datetime.now(UTC) - timedelta(seconds=10)

        service, session, _user = _make_service_with_user(prompt=prompt)

        submitted_data = {"field1": "test value"}

        with (
            patch("syntara.forms.services.form_prompt_service.validate_form_submission") as mock_validate,
            patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as mock_client_cls,
            patch("syntara.forms.services.form_prompt_service.AuditEventDispatcher") as mock_dispatcher,
        ):
            mock_validate.return_value = submitted_data
            mock_client = Mock()
            # Signal sending fails
            mock_client.send_form_signal = AsyncMock(side_effect=Exception("Network error"))
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # Should not raise - graceful degradation
            await service.submit(prompt_id, submitted_data)

            # Should still commit the database changes
            session.commit.assert_called_once()

            # Should still emit telemetry
            mock_dispatcher.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_not_found_raises_error(self) -> None:
        """Submitting non-existent prompt raises FormPromptNotFoundError."""
        prompt_id = uuid4()
        service, _session, _user = _make_service_with_user(prompt=None)

        with patch("syntara.forms.services.form_prompt_service.validate_form_submission"):
            with pytest.raises(FormPromptNotFoundError, match=str(prompt_id)):
                await service.submit(prompt_id, {})

    @pytest.mark.asyncio
    async def test_submit_expired_raises_error(self) -> None:
        """Submitting expired prompt raises FormPromptExpiredError."""
        prompt_id = uuid4()
        prompt = Mock(spec=FormPrompt)
        prompt.id = prompt_id
        prompt.status = FormPromptStatus.EXPIRED
        prompt.timeout_at = datetime.now(UTC) - timedelta(hours=1)
        prompt.form_definition = _MINIMAL_FORM_DEFINITION

        service, _session, _user = _make_service_with_user(prompt=prompt)

        with patch("syntara.forms.services.form_prompt_service.validate_form_submission") as mock_validate:
            # validate_submission should raise
            mock_validate.side_effect = FormPromptExpiredError(prompt_id, prompt.timeout_at)

            with pytest.raises(FormPromptExpiredError):
                await service.submit(prompt_id, {})

    @pytest.mark.asyncio
    async def test_submit_cancelled_raises_error(self) -> None:
        """Submitting cancelled prompt raises FormPromptCancelledError."""
        prompt_id = uuid4()
        prompt = Mock(spec=FormPrompt)
        prompt.id = prompt_id
        prompt.status = FormPromptStatus.CANCELLED
        prompt.form_definition = _MINIMAL_FORM_DEFINITION

        service, _session, _user = _make_service_with_user(prompt=prompt)

        with patch("syntara.forms.services.form_prompt_service.validate_form_submission") as mock_validate:
            # validate_submission should raise
            mock_validate.side_effect = FormPromptCancelledError(prompt_id)

            with pytest.raises(FormPromptCancelledError):
                await service.submit(prompt_id, {})

    @pytest.mark.asyncio
    async def test_submit_already_submitted_raises_error(self) -> None:
        """A prompt already marked submitted raises FormPromptAlreadyRespondedError."""
        prompt_id = uuid4()
        prompt = Mock(spec=FormPrompt)
        prompt.id = prompt_id
        prompt.status = FormPromptStatus.SUBMITTED  # Already submitted
        prompt.timeout_at = None
        prompt.form_definition = _MINIMAL_FORM_DEFINITION
        prompt.execution_id = uuid4()
        prompt.prompt_node_id = "form1"
        prompt.temporal_activity_id = "form1"
        prompt.created_at = datetime.now(UTC) - timedelta(seconds=10)

        service, _session, _user = _make_service_with_user(prompt=prompt)

        submitted_data = {"field1": "test value"}

        with pytest.raises(FormPromptAlreadyRespondedError):
            await service.submit(prompt_id, submitted_data)
