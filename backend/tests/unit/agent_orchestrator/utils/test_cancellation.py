"""Unit tests for invocation cancellation helpers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.exceptions import InvocationCancelledError
from syntara.agent_orchestrator.models.invocation import InvocationStatus
from syntara.agent_orchestrator.utils.cancellation import (
    get_invocation_cancel_key,
    is_invocation_cancelled,
    raise_if_invocation_cancelled,
)


def _db_session(invocation: MagicMock | None = None, *, get_side_effect: Exception | None = None) -> AsyncMock:
    session = AsyncMock()
    if get_side_effect is not None:
        session.get = AsyncMock(side_effect=get_side_effect)
    else:
        session.get = AsyncMock(return_value=invocation)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _stream_client(*, key_exists: bool = False, error: Exception | None = None) -> MagicMock:
    mock_client = AsyncMock()
    if error is not None:
        mock_client.key_exists = AsyncMock(side_effect=error)
    else:
        mock_client.key_exists = AsyncMock(return_value=key_exists)
    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_cls


def test_get_invocation_cancel_key_format() -> None:
    invocation_id = uuid4()
    assert get_invocation_cancel_key(invocation_id) == f"invocation:{invocation_id}:cancelled"


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
async def test_raise_if_cancelled_raises_on_redis_key() -> None:
    invocation_id = uuid4()
    session = _db_session()

    with (
        patch(
            "syntara.agent_orchestrator.utils.cancellation.StreamClient",
            _stream_client(key_exists=True),
        ),
        patch(
            "syntara.agent_orchestrator.utils.cancellation.AsyncSessionLocal",
            return_value=session,
        ),
        pytest.raises(InvocationCancelledError),
    ):
        await raise_if_invocation_cancelled(invocation_id, "orchestration")

    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_raise_if_cancelled_skips_db_when_redis_says_not_cancelled() -> None:
    session = _db_session()

    with (
        patch(
            "syntara.agent_orchestrator.utils.cancellation.StreamClient",
            _stream_client(key_exists=False),
        ),
        patch(
            "syntara.agent_orchestrator.utils.cancellation.AsyncSessionLocal",
            return_value=session,
        ),
    ):
        await raise_if_invocation_cancelled(uuid4(), "orchestration")

    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_raise_if_cancelled_db_fallback_on_redis_error() -> None:
    invocation_id = uuid4()
    invocation = MagicMock()
    invocation.status = InvocationStatus.CANCELLED
    session = _db_session(invocation)

    with (
        patch(
            "syntara.agent_orchestrator.utils.cancellation.StreamClient",
            _stream_client(error=ConnectionError("redis down")),
        ),
        patch(
            "syntara.agent_orchestrator.utils.cancellation.AsyncSessionLocal",
            return_value=session,
        ),
        pytest.raises(InvocationCancelledError),
    ):
        await raise_if_invocation_cancelled(invocation_id, "orchestration")

    session.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_raise_if_cancelled_db_fallback_on_redis_hang() -> None:
    """A hung Redis EXISTS must fall back to the invocation row, not block."""
    invocation_id = uuid4()
    invocation = MagicMock()
    invocation.status = InvocationStatus.CANCELLED
    session = _db_session(invocation)

    async def _hang(_key: str) -> bool:
        await asyncio.sleep(60)
        return False

    mock_client = AsyncMock()
    mock_client.key_exists = _hang
    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("syntara.agent_orchestrator.utils.cancellation._REDIS_CANCEL_CHECK_TIMEOUT_SECONDS", 0.05),
        patch("syntara.agent_orchestrator.utils.cancellation.StreamClient", mock_cls),
        patch(
            "syntara.agent_orchestrator.utils.cancellation.AsyncSessionLocal",
            return_value=session,
        ),
        pytest.raises(InvocationCancelledError),
    ):
        await raise_if_invocation_cancelled(invocation_id, "tool_execution")

    session.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_raise_if_cancelled_swallows_db_errors() -> None:
    session = _db_session(get_side_effect=OSError("down"))

    with (
        patch(
            "syntara.agent_orchestrator.utils.cancellation.StreamClient",
            _stream_client(error=ConnectionError("redis down")),
        ),
        patch(
            "syntara.agent_orchestrator.utils.cancellation.AsyncSessionLocal",
            return_value=session,
        ),
    ):
        await raise_if_invocation_cancelled(uuid4(), "orchestration")
