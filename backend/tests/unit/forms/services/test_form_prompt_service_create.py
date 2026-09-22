"""Unit tests for FormPromptService.create method.

Tests verify form prompt creation logic including validation,
duplicate detection, and database operations.
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.forms.exceptions import FormPromptAlreadyRequestedError
from syntara.forms.models.api_models import FormPromptCreateRequest
from syntara.forms.models.form_prompt import FormPrompt
from syntara.forms.services.form_prompt_service import FormPromptService

# Minimal valid form definition for tests
_MINIMAL_FORM_DEFINITION = {
    "fields": [{"value_name": "field1", "type": "text", "label": "Test Field", "required": False}]
}


def _make_service(*, raise_integrity_error: bool = False) -> tuple[FormPromptService, Mock]:
    """Build FormPromptService with mocked session."""
    session = Mock(spec=AsyncSession)

    session.add = Mock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()

    if raise_integrity_error:
        # Simulate uniqueness constraint violation
        orig_error = Exception('duplicate key value violates unique constraint "uix_execution_prompt_node_path"')
        session.commit = AsyncMock(
            side_effect=IntegrityError(
                'duplicate key value violates unique constraint "uix_execution_prompt_node_path"',
                params=None,
                orig=orig_error,
            )
        )
    else:
        session.commit = AsyncMock()

    # Create mock user for BaseService
    user = Mock()
    user.id = uuid4()

    svc = FormPromptService(session=session, user=user)
    return svc, session


class TestFormPromptServiceCreate:
    """Test FormPromptService.create method."""

    @pytest.mark.asyncio
    async def test_success_returns_form_prompt(self) -> None:
        """Successful creation returns FormPrompt with correct fields."""
        service, _session = _make_service()

        exec_id = uuid4()
        proj_id = uuid4()
        request = FormPromptCreateRequest(
            execution_id=exec_id,
            project_id=proj_id,
            prompt_node_id="form1",
            name="Test Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
        )

        result = await service.create(request)

        assert result.execution_id == exec_id
        assert result.project_id == proj_id
        assert result.prompt_node_id == "form1"
        assert result.name == "Test Form"
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_success_adds_to_session(self) -> None:
        """Session.add is called with the new FormPrompt."""
        service, session = _make_service()

        request = FormPromptCreateRequest(
            execution_id=uuid4(),
            project_id=uuid4(),
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
        )

        await service.create(request)

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, FormPrompt)

    @pytest.mark.asyncio
    async def test_duplicate_raises_form_prompt_already_requested_error(self) -> None:
        """Duplicate (execution_id, prompt_node_id, loop_iteration_path) raises error."""
        service, _ = _make_service(raise_integrity_error=True)

        exec_id = uuid4()
        request = FormPromptCreateRequest(
            execution_id=exec_id,
            project_id=uuid4(),
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            loop_iteration_path=[],
        )

        with pytest.raises(FormPromptAlreadyRequestedError, match="already exists"):
            await service.create(request)

    @pytest.mark.asyncio
    async def test_temporal_activity_id_uses_provided_value(self) -> None:
        """temporal_activity_id is set from request when provided."""
        service, session = _make_service()

        request = FormPromptCreateRequest(
            execution_id=uuid4(),
            project_id=uuid4(),
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            temporal_activity_id="form1_iter_0",
        )

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
            project_id=uuid4(),
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            responder_user_ids=[user1, user2],
        )

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
            project_id=uuid4(),
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            responder_group_ids=[group1],
        )

        await service.create(request)

        # Should add FormPrompt + 1 group junction
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_loop_iteration_path_stored_correctly(self) -> None:
        """loop_iteration_path is stored in the FormPrompt."""
        service, session = _make_service()

        request = FormPromptCreateRequest(
            execution_id=uuid4(),
            project_id=uuid4(),
            prompt_node_id="form1",
            name="Form",
            form_definition=_MINIMAL_FORM_DEFINITION,
            loop_iteration_path=[0, 1],
        )

        await service.create(request)

        added = session.add.call_args[0][0]
        assert added.loop_iteration_path == [0, 1]
