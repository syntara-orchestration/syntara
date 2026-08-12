"""Test fixtures and helpers for token usage tests."""

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation
from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord
from syntara.core.models import User


class TokenUsageFactory:
    """Factory for creating invocations with linked token usage records."""

    def __init__(self, session: AsyncSession, user: User, project_id: UUID) -> None:
        """Initialize with database session, user, and project ID."""
        self.session = session
        self.user = user
        self.project_id = project_id

    async def create(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        timestamp: datetime | None = None,
    ) -> tuple[Invocation, TokenUsageRecord]:
        """Create an invocation with a linked token usage record."""
        ts = timestamp or datetime.now(UTC)
        inv = Invocation(
            prompt=f"test {model_name} prompt",
            session_id="test-session",
            created_by=self.user.id,
            project_id=self.project_id,
            model_name=model_name,
        )
        self.session.add(inv)
        await self.session.flush()
        record = TokenUsageRecord(
            user_id=self.user.id,
            token_count=prompt_tokens + completion_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            invocation_id=inv.id,
            request_timestamp=ts,
        )
        self.session.add(record)
        await self.session.flush()
        return inv, record

    async def create_many(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        count: int,
        *,
        timestamp: datetime | None = None,
    ) -> list[tuple[Invocation, TokenUsageRecord]]:
        """Create multiple invocations with token records for the same model."""
        return [
            await self.create(model_name, prompt_tokens, completion_tokens, timestamp=timestamp) for _ in range(count)
        ]
