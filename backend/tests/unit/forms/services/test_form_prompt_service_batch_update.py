"""Unit tests for audit events emitted by form prompt status transitions."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.forms.models.api_models import (
    BatchFormPromptRequest,
    BatchFormPromptStatus,
    BatchFormPromptUpdate,
    FormPromptStatus,
)
from syntara.forms.models.form_prompt import FormPrompt
from syntara.forms.services.form_prompt_service import FormPromptService


def _make_service(
    prompts: list[FormPrompt],
    *,
    execution: SimpleNamespace | None = None,
    update_rowcounts: list[int] | None = None,
) -> tuple[FormPromptService, Mock]:
    session = Mock(spec=AsyncSession)
    user = Mock(id=uuid4())
    prompt_result = Mock()
    prompt_result.all.return_value = prompts
    execution_result = Mock()
    execution_result.all.return_value = [execution] if execution is not None else []
    update_results = []
    for rowcount in update_rowcounts or []:
        update_result = Mock()
        update_result.rowcount = rowcount
        update_results.append(update_result)
    session.exec = AsyncMock(side_effect=[prompt_result, execution_result, *update_results])
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return FormPromptService(session=session, user=user), session


def _make_prompt(status: FormPromptStatus = FormPromptStatus.PENDING) -> FormPrompt:
    prompt = Mock(spec=FormPrompt)
    prompt.id = uuid4()
    prompt.execution_id = uuid4()
    prompt.prompt_node_id = "collect_input"
    prompt.status = status
    prompt.timeout_at = datetime.now(UTC)
    return prompt


def _expire_request(*prompt_ids: object) -> BatchFormPromptRequest:
    return BatchFormPromptRequest(
        updates=[
            BatchFormPromptUpdate(prompt_id=prompt_id, status=BatchFormPromptStatus.EXPIRED) for prompt_id in prompt_ids
        ]
    )


@pytest.mark.asyncio
async def test_expiry_dispatches_after_commit_for_actual_transition() -> None:
    prompt = _make_prompt()
    workflow_id = uuid4()
    initiated_by = uuid4()
    execution = SimpleNamespace(id=prompt.execution_id, workflow_id=workflow_id, created_by=initiated_by)
    service, session = _make_service([prompt], execution=execution, update_rowcounts=[1])
    order: list[str] = []

    async def commit() -> None:
        order.append("commit")

    session.commit.side_effect = commit

    with patch("syntara.forms.services.form_prompt_service.AuditEventDispatcher") as dispatcher:
        dispatcher.dispatch.side_effect = lambda _event: order.append("dispatch")
        result = await service.batch_update_status(_expire_request(prompt.id))

    assert result.total_success == 1
    dispatcher.dispatch.assert_called_once()
    event = dispatcher.dispatch.call_args.args[0]
    assert event.prompt_id == prompt.id
    assert event.workflow_id == workflow_id
    assert event.execution_id == prompt.execution_id
    assert event.prompt_node_id == prompt.prompt_node_id
    assert event.initiated_by == initiated_by
    assert event.expired_at.tzinfo is not None
    assert event.timeout_at == prompt.timeout_at
    assert order == ["commit", "dispatch"]


@pytest.mark.asyncio
async def test_idempotent_expiry_does_not_dispatch_another_event() -> None:
    prompt = _make_prompt(FormPromptStatus.EXPIRED)
    service, session = _make_service([prompt])

    with patch("syntara.forms.services.form_prompt_service.AuditEventDispatcher") as dispatcher:
        result = await service.batch_update_status(_expire_request(prompt.id))

    assert result.total_success == 1
    assert result.results[0].message == "Already expired"
    dispatcher.dispatch.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_expiry_transition_does_not_dispatch() -> None:
    prompt = _make_prompt()
    workflow_id = uuid4()
    execution = SimpleNamespace(id=prompt.execution_id, workflow_id=workflow_id, created_by=uuid4())
    service, session = _make_service([prompt], execution=execution, update_rowcounts=[0])

    with patch("syntara.forms.services.form_prompt_service.AuditEventDispatcher") as dispatcher:
        result = await service.batch_update_status(_expire_request(prompt.id))

    assert result.total_success == 0
    assert result.total_failed == 1
    dispatcher.dispatch.assert_not_called()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiring_orphaned_prompt_keeps_missing_workflow_context_optional() -> None:
    """A soft-referenced prompt can expire after its parent execution is deleted."""
    prompt = _make_prompt()
    service, _session = _make_service([prompt], execution=None, update_rowcounts=[1])

    with patch("syntara.forms.services.form_prompt_service.AuditEventDispatcher") as dispatcher:
        result = await service.batch_update_status(_expire_request(prompt.id))

    assert result.total_success == 1
    event = dispatcher.dispatch.call_args.args[0]
    assert event.execution_id == prompt.execution_id
    assert event.workflow_id is None
    assert event.initiated_by is None
