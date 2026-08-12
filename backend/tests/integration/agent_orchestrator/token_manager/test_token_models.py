"""Unit tests for token counting data models."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord, UserTokenConfig
from syntara.core.models import User

# UserTokenConfig Tests


@pytest.mark.asyncio
async def test_user_token_config_creation(test_db_session: AsyncSession, test_user: User) -> None:
    """Test valid creation with BaseResource inheritance."""
    config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=10000,
        window_duration_seconds=86400,
    )
    test_db_session.add(config)
    await test_db_session.commit()

    # Verify BaseResource fields are present
    assert config.id is not None
    assert config.created_at is not None
    assert config.updated_at is not None
    assert isinstance(config.labels, dict)

    # Verify domain fields
    assert config.user_id == test_user.id
    assert config.token_limit == 10000
    assert config.window_duration_seconds == 86400


@pytest.mark.asyncio
async def test_user_token_config_requires_positive_limit(test_db_session: AsyncSession, test_user: User) -> None:
    """Test validation: token_limit > 0."""
    with pytest.raises(ValueError, match="greater than 0"):
        UserTokenConfig(
            user_id=test_user.id,
            token_limit=0,  # Invalid: must be > 0
            window_duration_seconds=3600,
        )


@pytest.mark.asyncio
async def test_user_token_config_requires_positive_window(test_db_session: AsyncSession, test_user: User) -> None:
    """Test validation: window_duration_seconds > 0."""
    with pytest.raises(ValueError, match="greater than 0"):
        UserTokenConfig(
            user_id=test_user.id,
            token_limit=5000,
            window_duration_seconds=0,  # Invalid: must be > 0
        )


@pytest.mark.asyncio
async def test_user_token_config_unique_user_id(test_db_session: AsyncSession, test_user: User) -> None:
    """Test DB constraint: unique user_id."""
    # Create first config
    config1 = UserTokenConfig(
        user_id=test_user.id,
        token_limit=10000,
        window_duration_seconds=86400,
    )
    test_db_session.add(config1)
    await test_db_session.commit()

    # Try to create duplicate config for same user
    config2 = UserTokenConfig(
        user_id=test_user.id,
        token_limit=5000,
        window_duration_seconds=3600,
    )
    test_db_session.add(config2)

    with pytest.raises(IntegrityError):
        await test_db_session.commit()


@pytest.mark.asyncio
async def test_user_token_config_timestamps(test_db_session: AsyncSession, test_user: User) -> None:
    """Test created_at, updated_at auto-set by BaseResource."""
    config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=10000,
        window_duration_seconds=86400,
    )
    test_db_session.add(config)
    await test_db_session.commit()

    # Verify timestamps are set
    assert config.created_at is not None
    assert config.updated_at is not None

    # Timestamps should be timezone-aware
    assert config.created_at.tzinfo is not None
    assert config.updated_at.tzinfo is not None


@pytest.mark.asyncio
async def test_user_token_config_has_labels(test_db_session: AsyncSession, test_user: User) -> None:
    """Test verify labels field inherited from BaseResource."""
    config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=10000,
        window_duration_seconds=86400,
        labels={"environment": "test", "priority": "high"},
    )
    test_db_session.add(config)
    await test_db_session.commit()

    assert config.labels == {"environment": "test", "priority": "high"}


# TokenUsageRecord Tests


@pytest.mark.asyncio
async def test_token_usage_record_creation(test_db_session: AsyncSession, test_user: User) -> None:
    """Test valid creation with BaseResource inheritance."""
    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=1500,
    )
    test_db_session.add(record)
    await test_db_session.commit()

    # Verify BaseResource fields
    assert record.id is not None
    assert record.created_at is not None
    assert record.updated_at is not None
    assert isinstance(record.labels, dict)

    # Verify domain fields
    assert record.user_id == test_user.id
    assert record.token_count == 1500
    assert record.request_timestamp is not None


@pytest.mark.asyncio
async def test_token_usage_record_non_negative_count(test_db_session: AsyncSession, test_user: User) -> None:
    """Test validation: token_count >= 0."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        TokenUsageRecord(
            user_id=test_user.id,
            token_count=-100,  # Invalid: must be >= 0
        )


@pytest.mark.asyncio
async def test_token_usage_record_timestamp_defaults(test_db_session: AsyncSession, test_user: User) -> None:
    """Test request_timestamp defaults to now."""
    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=500,
    )
    test_db_session.add(record)
    await test_db_session.commit()

    # request_timestamp should be set automatically
    assert record.request_timestamp is not None


@pytest.mark.asyncio
async def test_token_usage_record_has_labels(test_db_session: AsyncSession, test_user: User) -> None:
    """Test verify labels field inherited from BaseResource."""
    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=750,
        labels={"source": "api", "endpoint": "/generate"},
    )
    test_db_session.add(record)
    await test_db_session.commit()

    assert record.labels == {"source": "api", "endpoint": "/generate"}


@pytest.mark.asyncio
async def test_token_usage_record_created_at_vs_request_timestamp(
    test_db_session: AsyncSession, test_user: User
) -> None:
    """Test verify created_at (DB insert time) differs from request_timestamp (request time)."""
    # Create record with explicit request_timestamp in the past
    past_time = datetime.now(UTC) - timedelta(hours=2)

    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=250,
        request_timestamp=past_time,
    )
    test_db_session.add(record)
    await test_db_session.commit()

    # created_at should be recent (DB insert time)
    # request_timestamp should be the past time we set
    assert record.created_at > record.request_timestamp
    assert (record.created_at - past_time).total_seconds() > 7000  # More than ~2 hours


# Post-LLM Token Fields Tests (T001)


@pytest.mark.asyncio
async def test_token_usage_record_new_fields_default_null(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that new post-LLM fields default to None when not provided."""
    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=1500,
    )
    test_db_session.add(record)
    await test_db_session.commit()

    assert record.estimated_input_tokens is None
    assert record.prompt_tokens is None
    assert record.completion_tokens is None
    assert record.invocation_id is None
    assert record.usage_details is None


@pytest.mark.asyncio
async def test_token_usage_record_with_estimated_input_tokens(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a record with estimated_input_tokens set (pre-LLM scenario)."""
    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=1500,
        estimated_input_tokens=1500,
    )
    test_db_session.add(record)
    await test_db_session.commit()

    assert record.estimated_input_tokens == 1500
    assert record.prompt_tokens is None
    assert record.completion_tokens is None


@pytest.mark.asyncio
async def test_token_usage_record_with_actual_tokens(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a record with all post-LLM fields populated."""
    usage_details = [{"prompt_tokens": 943, "completion_tokens": 500, "total_tokens": 1443}]
    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=1443,
        estimated_input_tokens=1500,
        prompt_tokens=943,
        completion_tokens=500,
        usage_details=usage_details,
    )
    test_db_session.add(record)
    await test_db_session.commit()

    assert record.estimated_input_tokens == 1500
    assert record.prompt_tokens == 943
    assert record.completion_tokens == 500
    assert record.usage_details == usage_details


@pytest.mark.asyncio
async def test_token_usage_record_invocation_id(
    test_db_session: AsyncSession, test_user: User, test_project_id
) -> None:
    """Test that invocation_id can be set as a UUID referencing an invocation."""
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
        token_count=1000,
        invocation_id=invocation.id,
    )
    test_db_session.add(record)
    await test_db_session.commit()

    assert record.invocation_id == invocation.id


@pytest.mark.asyncio
async def test_token_usage_record_non_negative_estimated_input_tokens(
    test_db_session: AsyncSession, test_user: User
) -> None:
    """Test validation: estimated_input_tokens >= 0."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        TokenUsageRecord(
            user_id=test_user.id,
            token_count=100,
            estimated_input_tokens=-1,
        )


@pytest.mark.asyncio
async def test_token_usage_record_non_negative_prompt_tokens(test_db_session: AsyncSession, test_user: User) -> None:
    """Test validation: prompt_tokens >= 0."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        TokenUsageRecord(
            user_id=test_user.id,
            token_count=100,
            prompt_tokens=-1,
        )


@pytest.mark.asyncio
async def test_token_usage_record_non_negative_completion_tokens(
    test_db_session: AsyncSession, test_user: User
) -> None:
    """Test validation: completion_tokens >= 0."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        TokenUsageRecord(
            user_id=test_user.id,
            token_count=100,
            completion_tokens=-1,
        )


@pytest.mark.asyncio
async def test_token_usage_record_zero_completion_tokens(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that completion_tokens=0 is valid (empty LLM response edge case)."""
    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=943,
        estimated_input_tokens=1000,
        prompt_tokens=943,
        completion_tokens=0,
    )
    test_db_session.add(record)
    await test_db_session.commit()

    assert record.completion_tokens == 0
