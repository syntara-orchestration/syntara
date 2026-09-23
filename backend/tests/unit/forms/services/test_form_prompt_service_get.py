"""Tests for FormPromptService.get."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import Group, User
from syntara.core.models.user_reference import UserReference
from syntara.forms.exceptions import FormPromptNotFoundError
from syntara.forms.models.api_models import FormPromptStatus, ResponderGroupSummary, ResponderUserSummary
from syntara.forms.models.form_prompt import FormPrompt
from syntara.forms.services.form_prompt_service import FormPromptService
from tests.unit.fixtures.form import create_test_form_prompt


def _make_service(prompt: FormPrompt | None) -> FormPromptService:
    """Build a service whose query returns the given prompt."""
    session = Mock(spec=AsyncSession)
    result = Mock()
    result.one_or_none.return_value = prompt
    session.exec = AsyncMock(return_value=result)
    user = Mock()
    user.id = uuid4()
    return FormPromptService(session=session, user=user)


class TestFormPromptServiceGet:
    """Tests for loading one form prompt with all response relationships."""

    @pytest.mark.asyncio
    async def test_get_returns_form_prompt(self) -> None:
        prompt = create_test_form_prompt(name="Expense approval")

        response = await _make_service(prompt).get(prompt.id)

        assert response.id == prompt.id
        assert response.name == "Expense approval"
        assert response.status == FormPromptStatus.PENDING
        assert response.form_definition == prompt.form_definition

    @pytest.mark.asyncio
    async def test_get_raises_not_found_for_unknown_id(self) -> None:
        prompt_id = uuid4()

        with pytest.raises(FormPromptNotFoundError):
            await _make_service(None).get(prompt_id)

    @pytest.mark.asyncio
    async def test_get_populates_responder_users(self) -> None:
        prompt = create_test_form_prompt()
        first = User(username="ada", first_name="Ada", last_name="Lovelace")
        second = User(username="grace", first_name="Grace", last_name="Hopper")
        prompt.responder_user_records = [first, second]

        response = await _make_service(prompt).get(prompt.id)

        assert response.responder_users == [
            ResponderUserSummary(id=first.id, username="ada"),
            ResponderUserSummary(id=second.id, username="grace"),
        ]

    @pytest.mark.asyncio
    async def test_get_populates_responder_groups(self) -> None:
        prompt = create_test_form_prompt()
        group = Group(name="Approvers")
        prompt.responder_group_records = [group]

        response = await _make_service(prompt).get(prompt.id)

        assert response.responder_groups == [ResponderGroupSummary(id=group.id, name="Approvers")]

    @pytest.mark.asyncio
    async def test_get_empty_responder_lists(self) -> None:
        prompt = create_test_form_prompt()

        response = await _make_service(prompt).get(prompt.id)

        assert response.responder_users == []
        assert response.responder_groups == []

    @pytest.mark.asyncio
    async def test_get_populates_responded_by_reference(self) -> None:
        prompt = create_test_form_prompt(
            status=FormPromptStatus.SUBMITTED,
            responded_by=uuid4(),
            responded_at=datetime.now(UTC),
            response_data={"reason": "ready"},
        )
        prompt.responder = User(username="ada", first_name="Ada", last_name="Lovelace")

        response = await _make_service(prompt).get(prompt.id)

        assert response.responded_by == UserReference(id=prompt.responded_by, name="Ada Lovelace")

    @pytest.mark.asyncio
    async def test_get_responded_by_none_when_pending(self) -> None:
        prompt = create_test_form_prompt()

        response = await _make_service(prompt).get(prompt.id)

        assert response.responded_by is None

    @pytest.mark.asyncio
    async def test_get_signal_delivery_error_is_none(self) -> None:
        prompt = create_test_form_prompt()
        prompt.signal_delivery_error = "transient signal error"

        response = await _make_service(prompt).get(prompt.id)

        assert response.signal_delivery_error is None
