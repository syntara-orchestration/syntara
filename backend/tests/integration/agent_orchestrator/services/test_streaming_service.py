"""Integration tests for WebSocketStreamingHandler invocation lookup."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.agent_orchestrator.services.streaming_service import WebSocketStreamingHandler
from syntara.core.models import User

pytestmark = pytest.mark.integration


class TestWebSocketStreamingHandlerCheckInvocationExists:
    """Integration tests for _check_invocation_exists against PostgreSQL."""

    async def test_check_invocation_exists_returns_status_from_db_aap_86853(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
        test_project_id: UUID,
    ) -> None:
        """Regression AAP-86853: scalar lookup must return Invocation so .status works."""
        invocation_id = uuid4()
        test_db_session.add(
            Invocation(
                id=invocation_id,
                prompt="Regression test prompt",
                created_by=test_user.id,
                project_id=test_project_id,
                session_id="aap-86853-session",
                status=InvocationStatus.RUNNING,
            )
        )
        await test_db_session.commit()

        handler = WebSocketStreamingHandler(session_factory=test_db_session_factory)
        status = await handler._check_invocation_exists(invocation_id)

        assert status == InvocationStatus.RUNNING
