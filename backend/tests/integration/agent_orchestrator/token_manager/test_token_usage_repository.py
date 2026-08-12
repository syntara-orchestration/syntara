"""Unit tests for TokenUsageRepository."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.token_manager.exceptions import UserTokenConfigNotFoundError
from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord, UserTokenConfig
from syntara.agent_orchestrator.token_manager.repository import TokenUsageRepository

if TYPE_CHECKING:
    from syntara.core.models import User


@pytest.fixture
def repository() -> TokenUsageRepository:
    """Create a TokenUsageRepository instance."""
    return TokenUsageRepository()


@pytest_asyncio.fixture
async def user_config(test_db_session: AsyncSession, test_user) -> UserTokenConfig:
    """Create a test user configuration."""
    config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=10000,
        window_duration_seconds=3600,  # 1 hour
    )
    test_db_session.add(config)
    await test_db_session.commit()
    return config


@pytest.mark.asyncio
async def test_get_user_config(
    repository: TokenUsageRepository,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test fetching user configuration by user_id."""
    # Act
    result = await repository.get_user_config(user_config.user_id, test_db_session)

    # Assert
    assert result.id == user_config.id
    assert result.user_id == user_config.user_id
    assert result.token_limit == 10000
    assert result.window_duration_seconds == 3600


@pytest.mark.asyncio
async def test_get_user_config_not_found(
    repository: TokenUsageRepository,
    test_db_session: AsyncSession,
) -> None:
    """Test that UserTokenConfigNotFoundError is raised when config doesn't exist."""
    # Arrange
    non_existent_user_id = uuid4()

    # Act & Assert
    with pytest.raises(UserTokenConfigNotFoundError) as exc_info:
        await repository.get_user_config(non_existent_user_id, test_db_session)

    assert exc_info.value.user_id == non_existent_user_id


@pytest.mark.asyncio
async def test_get_user_config_with_lock(
    repository: TokenUsageRepository,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test fetching user configuration with row-level lock."""
    # Act
    async with test_db_session.begin_nested():
        result = await repository.get_user_config_with_lock(user_config.user_id, test_db_session)

        # Assert
        assert result.id == user_config.id
        assert result.user_id == user_config.user_id
        assert result.token_limit == 10000


@pytest.mark.asyncio
async def test_calculate_current_usage_empty(
    repository: TokenUsageRepository,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test calculating usage for a user with no usage records returns 0."""
    # Act
    usage = await repository.calculate_current_usage(
        user_id=user_config.user_id,
        window_duration_seconds=3600,
        session=test_db_session,
    )

    # Assert
    assert usage == 0


@pytest.mark.asyncio
async def test_calculate_current_usage_within_window(
    repository: TokenUsageRepository,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test that recent usage records are included in calculation."""
    # Arrange - create usage records within the window
    now = datetime.now(UTC)
    records = [
        TokenUsageRecord(
            user_id=user_config.user_id,
            token_count=1000,
            request_timestamp=now - timedelta(minutes=30),
        ),
        TokenUsageRecord(
            user_id=user_config.user_id,
            token_count=2000,
            request_timestamp=now - timedelta(minutes=15),
        ),
    ]
    for record in records:
        test_db_session.add(record)
    await test_db_session.commit()

    # Act
    usage = await repository.calculate_current_usage(
        user_id=user_config.user_id,
        window_duration_seconds=3600,  # 1 hour window
        session=test_db_session,
    )

    # Assert
    assert usage == 3000  # 1000 + 2000


@pytest.mark.asyncio
async def test_calculate_current_usage_excludes_old(
    repository: TokenUsageRepository,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test that old usage records outside the window are excluded."""
    # Arrange - create old and recent records
    now = datetime.now(UTC)
    old_record = TokenUsageRecord(
        user_id=user_config.user_id,
        token_count=5000,
        request_timestamp=now - timedelta(hours=2),  # Outside 1-hour window
    )
    recent_record = TokenUsageRecord(
        user_id=user_config.user_id,
        token_count=1000,
        request_timestamp=now - timedelta(minutes=30),  # Within window
    )
    test_db_session.add(old_record)
    test_db_session.add(recent_record)
    await test_db_session.commit()

    # Act
    usage = await repository.calculate_current_usage(
        user_id=user_config.user_id,
        window_duration_seconds=3600,  # 1 hour window
        session=test_db_session,
    )

    # Assert
    assert usage == 1000  # Only recent record counted


@pytest.mark.asyncio
async def test_record_usage(
    repository: TokenUsageRepository,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test creating a new usage record."""
    # Act
    record = await repository.record_usage(
        user_id=user_config.user_id,
        token_count=2500,
        session=test_db_session,
    )
    await test_db_session.commit()

    # Assert
    assert record.id is not None
    assert record.user_id == user_config.user_id
    assert record.token_count == 2500
    assert record.request_timestamp is not None

    # Verify it's in the database
    result = await test_db_session.exec(select(TokenUsageRecord).where(TokenUsageRecord.id == record.id))
    saved_record = result.one()
    assert saved_record.token_count == 2500


@pytest.mark.asyncio
async def test_update_user_config_existing(
    repository: TokenUsageRepository,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test updating an existing user configuration."""
    # Act
    updated_config = await repository.update_user_config(
        user_id=user_config.user_id,
        token_limit=20000,
        window_duration_seconds=7200,  # 2 hours
        session=test_db_session,
    )
    await test_db_session.commit()

    # Assert
    assert updated_config.id == user_config.id
    assert updated_config.token_limit == 20000
    assert updated_config.window_duration_seconds == 7200

    # Verify in database
    result = await test_db_session.exec(select(UserTokenConfig).where(UserTokenConfig.user_id == user_config.user_id))
    saved_config = result.one()
    assert saved_config.token_limit == 20000


@pytest.mark.asyncio
async def test_update_user_config_create_new(
    repository: TokenUsageRepository,
    test_db_session: AsyncSession,
    test_user,
) -> None:
    """Test creating a new configuration when none exists.

    Note: test_user doesn't have a config yet, so this test creates one.
    """
    # Act - create config for test_user (who has no config yet)
    config = await repository.update_user_config(
        user_id=test_user.id,
        token_limit=15000,
        window_duration_seconds=86400,  # 24 hours
        session=test_db_session,
    )
    await test_db_session.commit()

    # Assert
    assert config.id is not None
    assert config.user_id == test_user.id
    assert config.token_limit == 15000
    assert config.window_duration_seconds == 86400

    # Verify in database
    result = await test_db_session.exec(select(UserTokenConfig).where(UserTokenConfig.user_id == test_user.id))
    saved_config = result.one()
    assert saved_config.token_limit == 15000


# update_with_actual_token_usage Tests (T002)


@pytest_asyncio.fixture
async def token_record_with_invocation(
    test_db_session: AsyncSession, test_user: "User", user_config: UserTokenConfig, test_project_id
) -> TokenUsageRecord:
    """Create a token usage record with invocation_id set (simulating pre-LLM creation)."""
    from syntara.agent_orchestrator.models import Invocation, InvocationStatus

    invocation = Invocation(
        prompt="test prompt",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-001",
        status=InvocationStatus.RUNNING,
    )
    test_db_session.add(invocation)
    await test_db_session.flush()

    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=1500,
        estimated_input_tokens=1500,
        invocation_id=invocation.id,
    )
    test_db_session.add(record)
    await test_db_session.commit()
    return record


@pytest.mark.asyncio
async def test_update_with_actual_token_usage(
    repository: TokenUsageRepository,
    token_record_with_invocation: TokenUsageRecord,
    test_db_session: AsyncSession,
) -> None:
    """Test updating a record with actual token counts from the LLM provider."""
    record = token_record_with_invocation
    assert record.invocation_id is not None
    usage_details = [{"prompt_tokens": 943, "completion_tokens": 500, "total_tokens": 1443}]

    updated = await repository.update_with_actual_token_usage(
        invocation_id=record.invocation_id,
        prompt_tokens=943,
        completion_tokens=500,
        token_count=1443,
        usage_details=usage_details,
        session=test_db_session,
    )

    assert updated is True

    # Verify the record was updated in DB
    await test_db_session.refresh(record)
    assert record.prompt_tokens == 943
    assert record.completion_tokens == 500
    assert record.token_count == 1443
    assert record.usage_details == usage_details
    # estimated_input_tokens should be preserved
    assert record.estimated_input_tokens == 1500


@pytest.mark.asyncio
async def test_update_with_actual_token_usage_no_record_found(
    repository: TokenUsageRepository,
    test_db_session: AsyncSession,
) -> None:
    """Test that update_with_actual_token_usage returns False when no record matches invocation_id."""
    non_existent_id = uuid4()

    updated = await repository.update_with_actual_token_usage(
        invocation_id=non_existent_id,
        prompt_tokens=943,
        completion_tokens=500,
        token_count=1443,
        usage_details=[{"prompt_tokens": 943}],
        session=test_db_session,
    )

    assert updated is False


@pytest.mark.asyncio
async def test_update_with_actual_token_usage_zero_completion(
    repository: TokenUsageRepository,
    token_record_with_invocation: TokenUsageRecord,
    test_db_session: AsyncSession,
) -> None:
    """Test updating with zero completion tokens (empty LLM response)."""
    record = token_record_with_invocation
    assert record.invocation_id is not None

    updated = await repository.update_with_actual_token_usage(
        invocation_id=record.invocation_id,
        prompt_tokens=943,
        completion_tokens=0,
        token_count=943,
        usage_details=[{"prompt_tokens": 943, "completion_tokens": 0, "total_tokens": 943}],
        session=test_db_session,
    )

    assert updated is True
    await test_db_session.refresh(record)
    assert record.completion_tokens == 0
    assert record.token_count == 943


@pytest.mark.asyncio
async def test_update_with_actual_token_usage_rejects_mismatched_token_count(
    repository: TokenUsageRepository,
    token_record_with_invocation: TokenUsageRecord,
    test_db_session: AsyncSession,
) -> None:
    """Test that token_count must equal prompt_tokens + completion_tokens."""
    record = token_record_with_invocation
    assert record.invocation_id is not None

    with pytest.raises(ValueError, match=r"token_count.*must equal"):
        await repository.update_with_actual_token_usage(
            invocation_id=record.invocation_id,
            prompt_tokens=943,
            completion_tokens=500,
            token_count=9999,  # mismatch
            usage_details=[],
            session=test_db_session,
        )


# T006: record_usage with estimated_input_tokens and invocation_id


@pytest.mark.asyncio
async def test_record_usage_with_estimated_input_tokens(
    repository: TokenUsageRepository,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test that record_usage stores estimated_input_tokens when provided."""
    record = await repository.record_usage(
        user_id=user_config.user_id,
        token_count=1500,
        session=test_db_session,
        estimated_input_tokens=1500,
    )
    await test_db_session.commit()

    assert record.estimated_input_tokens == 1500
    assert record.token_count == 1500


@pytest.mark.asyncio
async def test_record_usage_with_invocation_id(
    repository: TokenUsageRepository,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
    test_user: "User",
    test_project_id,
) -> None:
    """Test that record_usage stores invocation_id when provided."""
    from syntara.agent_orchestrator.models import Invocation, InvocationStatus

    invocation = Invocation(
        prompt="test prompt",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-001",
        status=InvocationStatus.RUNNING,
    )
    test_db_session.add(invocation)
    await test_db_session.flush()

    record = await repository.record_usage(
        user_id=user_config.user_id,
        token_count=1500,
        session=test_db_session,
        estimated_input_tokens=1500,
        invocation_id=invocation.id,
    )
    await test_db_session.commit()

    assert record.invocation_id == invocation.id
    assert record.estimated_input_tokens == 1500
    # Post-LLM fields should still be None
    assert record.prompt_tokens is None
    assert record.completion_tokens is None
