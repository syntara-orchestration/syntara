"""Unit tests for invocation cancellation helpers."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.exceptions import InvocationCancelledError
from syntara.agent_orchestrator.models.invocation import InvocationStatus
from syntara.agent_orchestrator.utils.cancellation import (
    is_invocation_cancelled,
    raise_if_invocation_cancelled,
)


@pytest.mark.asyncio
async def test_is_invocation_cancelled_true() -> None:
    invocation = MagicMock()
    invocation.status = InvocationStatus.CANCELLED
    session = AsyncMock()
    session.get = AsyncMock(return_value=invocation)

    assert await is_invocation_cancelled(session, uuid4()) is True


@pytest.mark.asyncio
async def test_is_invocation_cancelled_false_for_running() -> None:
    invocation = MagicMock()
    invocation.status = InvocationStatus.RUNNING
    session = AsyncMock()
    session.get = AsyncMock(return_value=invocation)

    assert await is_invocation_cancelled(session, uuid4()) is False


@pytest.mark.asyncio
async def test_is_invocation_cancelled_false_when_missing() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    assert await is_invocation_cancelled(session, uuid4()) is False


@pytest.mark.asyncio
async def test_raise_if_cancelled_raises() -> None:
    invocation_id = uuid4()
    invocation = MagicMock()
    invocation.status = InvocationStatus.CANCELLED
    session = AsyncMock()
    session.get = AsyncMock(return_value=invocation)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "syntara.agent_orchestrator.utils.cancellation.AsyncSessionLocal",
        return_value=session,
    ):
        with pytest.raises(InvocationCancelledError):
            await raise_if_invocation_cancelled(invocation_id, "orchestration")


@pytest.mark.asyncio
async def test_raise_if_cancelled_swallows_db_errors() -> None:
    session = AsyncMock()
    session.get = AsyncMock(side_effect=OSError("down"))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "syntara.agent_orchestrator.utils.cancellation.AsyncSessionLocal",
        return_value=session,
    ):
        await raise_if_invocation_cancelled(uuid4(), "orchestration")
