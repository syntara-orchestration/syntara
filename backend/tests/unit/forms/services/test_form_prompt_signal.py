"""Tests for resolving Form Prompt activity signals from persisted submissions."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models.user import User
from syntara.forms.models.api_models import FormPromptStatus
from syntara.forms.services.form_prompt_signal import (
    NotFormPromptSignal,
    RejectedFormPromptSignal,
    VerifiedFormPromptSignal,
    build_form_prompt_signal_payload,
    resolve_verified_form_prompt_signal,
)
from tests.unit.fixtures.form import create_submitted_form_prompt, create_test_form_prompt


def _session_with_prompts(*prompts: object, responder: object | None = None) -> AsyncMock:
    """Create a mocked session returning the supplied prompt rows."""
    session = AsyncMock(spec=AsyncSession)
    query_result = Mock()
    query_result.all.return_value = list(prompts)
    session.exec.return_value = query_result
    session.get.return_value = responder
    return session


class TestBuildFormPromptSignalPayload:
    """Tests for the canonical Form Prompt signal shape."""

    def test_builds_payload_with_nullable_responder_username(self) -> None:
        responded_at = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
        prompt = create_test_form_prompt(
            responded_by=None,
            responded_at=responded_at,
            response_data={"reason": "persisted"},
            prompt_node_id="prompt",
            status=FormPromptStatus.SUBMITTED,
        )
        prompt.id = uuid4()

        payload = build_form_prompt_signal_payload(prompt, responded_by_username=None)

        assert payload == {
            "outcome": "submitted",
            "response_data": {"reason": "persisted"},
            "responded_by": None,
            "responded_at": responded_at.isoformat(),
            "prompt_id": str(prompt.id),
        }


class TestResolveVerifiedFormPromptSignal:
    """Tests for Form Prompt callback resolution and state verification."""

    @pytest.mark.asyncio
    async def test_returns_not_form_prompt_when_no_row_matches(self) -> None:
        session = _session_with_prompts()

        result = await resolve_verified_form_prompt_signal(session, uuid4(), "agentic-node")

        assert isinstance(result, NotFormPromptSignal)
        session.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_multiple_matching_rows(self) -> None:
        execution_id = uuid4()
        first = create_submitted_form_prompt(execution_id=execution_id, prompt_node_id="first")
        second = create_submitted_form_prompt(execution_id=execution_id, prompt_node_id="second")
        first.temporal_activity_id = second.temporal_activity_id = "ambiguous-temporal-id"
        session = _session_with_prompts(first, second)

        result = await resolve_verified_form_prompt_signal(session, execution_id, "ambiguous-temporal-id")

        assert isinstance(result, RejectedFormPromptSignal)
        assert result.reason == "multiple matching prompts"

    @pytest.mark.parametrize(
        "prompt_status",
        [FormPromptStatus.PENDING, FormPromptStatus.EXPIRED, FormPromptStatus.CANCELLED],
    )
    @pytest.mark.asyncio
    async def test_rejects_prompt_without_submitted_status(self, prompt_status: FormPromptStatus) -> None:
        execution_id = uuid4()
        prompt = create_test_form_prompt(
            execution_id=execution_id,
            prompt_node_id="prompt",
            status=prompt_status,
        )
        session = _session_with_prompts(prompt)

        result = await resolve_verified_form_prompt_signal(session, execution_id, prompt.temporal_activity_id)

        assert isinstance(result, RejectedFormPromptSignal)
        assert "prompt status" in result.reason
        session.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_db_derived_payload_for_submitted_prompt(self) -> None:
        execution_id = uuid4()
        responder_id = uuid4()
        prompt = create_submitted_form_prompt(
            execution_id=execution_id,
            prompt_node_id="prompt_iter_0",
            responded_by=responder_id,
            response_data={"reason": "persisted"},
        )
        prompt.temporal_activity_id = "prompt_iter_0"
        responder = SimpleNamespace(username="listed-responder")
        session = _session_with_prompts(prompt, responder=responder)

        result = await resolve_verified_form_prompt_signal(session, execution_id, "prompt_iter_0")

        assert isinstance(result, VerifiedFormPromptSignal)
        assert result.payload["response_data"] == {"reason": "persisted"}
        assert result.payload["responded_by"] == "listed-responder"
        session.get.assert_awaited_once_with(User, responder_id)

    @pytest.mark.parametrize("responder_username", ["responder", None])
    @pytest.mark.asyncio
    async def test_missing_responder_resolves_to_null_without_rejecting(self, responder_username: str | None) -> None:
        execution_id = uuid4()
        prompt = create_submitted_form_prompt(
            execution_id=execution_id,
            prompt_node_id="prompt",
            responded_by=uuid4(),
            response_data={"reason": "persisted"},
        )
        prompt.temporal_activity_id = "prompt"
        responder = SimpleNamespace(username=responder_username) if responder_username is not None else None
        session = _session_with_prompts(prompt, responder=responder)

        result = await resolve_verified_form_prompt_signal(session, execution_id, "prompt")

        assert isinstance(result, VerifiedFormPromptSignal)
        assert result.payload["responded_by"] == responder_username

    @pytest.mark.asyncio
    async def test_null_responder_does_not_query_user_table(self) -> None:
        execution_id = uuid4()
        prompt = create_test_form_prompt(
            execution_id=execution_id,
            prompt_node_id="prompt",
            status=FormPromptStatus.SUBMITTED,
            responded_by=None,
            responded_at=datetime.now(UTC),
            response_data={"reason": "persisted"},
        )
        session = _session_with_prompts(prompt)

        result = await resolve_verified_form_prompt_signal(session, execution_id, prompt.temporal_activity_id)

        assert isinstance(result, VerifiedFormPromptSignal)
        assert result.payload["responded_by"] is None
        session.get.assert_not_awaited()

    @pytest.mark.parametrize("missing_field", ["response_data", "responded_at"])
    @pytest.mark.asyncio
    async def test_rejects_submitted_row_missing_response_data_or_time(self, missing_field: str) -> None:
        execution_id = uuid4()
        prompt = create_submitted_form_prompt(execution_id=execution_id, prompt_node_id="prompt")
        if missing_field == "response_data":
            prompt.response_data = None
        else:
            prompt.responded_at = None
        session = _session_with_prompts(prompt)

        result = await resolve_verified_form_prompt_signal(session, execution_id, prompt.temporal_activity_id)

        assert isinstance(result, RejectedFormPromptSignal)
        assert result.reason == "submitted prompt has incomplete response data"
