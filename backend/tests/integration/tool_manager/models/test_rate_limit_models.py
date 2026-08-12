"""Unit tests for RateLimit models.

Tests cover:
- RateLimit creation with required fields
- TargetType enum
- Field validation and constraints
- Rate limit configuration scenarios
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.tool_manager.models.rate_limit_config import (
    RateLimit,
    TargetType,
)


@pytest.mark.asyncio
async def test_create_rate_limit_with_required_fields(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a rate limit with all required fields."""
    rate_limit_id = uuid4()
    target_id = str(uuid4())

    rate_limit = RateLimit(
        id=rate_limit_id,
        target_type=TargetType.PROVIDER,
        target_id=target_id,
        requests_per_window=100,
        window_duration_seconds=3600,  # 1 hour
        created_by=test_user.id,
    )
    test_db_session.add(rate_limit)
    await test_db_session.commit()

    assert rate_limit.id == rate_limit_id
    assert rate_limit.target_type == TargetType.PROVIDER
    assert rate_limit.target_id == target_id
    assert rate_limit.target_name is None  # Default value
    assert rate_limit.requests_per_window == 100
    assert rate_limit.window_duration_seconds == 3600
    assert rate_limit.burst_allowance == 0  # Default value
    assert rate_limit.enabled is True  # Default value
    assert rate_limit.current_usage == 0  # Default value
    assert rate_limit.usage_reset_at is None  # Default value
    assert rate_limit.created_by == test_user.id
    assert rate_limit.created_at is not None
    assert rate_limit.updated_at is not None


@pytest.mark.asyncio
async def test_create_rate_limit_with_all_fields(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a rate limit with all fields including optional ones."""
    rate_limit_id = uuid4()
    target_id = str(uuid4())
    now = datetime.now(UTC)
    reset_time = now + timedelta(hours=1)

    rate_limit = RateLimit(
        id=rate_limit_id,
        target_type=TargetType.TOOL,
        target_id=target_id,
        target_name="Test Tool Rate Limit",
        requests_per_window=50,
        window_duration_seconds=300,  # 5 minutes
        burst_allowance=10,
        enabled=False,
        current_usage=25,
        usage_reset_at=reset_time,
        created_by=test_user.id,
        labels={"env": "test", "priority": "high"},
    )
    test_db_session.add(rate_limit)
    await test_db_session.commit()

    assert rate_limit.target_type == TargetType.TOOL
    assert rate_limit.target_name == "Test Tool Rate Limit"
    assert rate_limit.requests_per_window == 50
    assert rate_limit.window_duration_seconds == 300
    assert rate_limit.burst_allowance == 10
    assert rate_limit.enabled is False
    assert rate_limit.current_usage == 25
    assert rate_limit.usage_reset_at == reset_time
    assert rate_limit.labels == {"env": "test", "priority": "high"}


def test_target_type_enum() -> None:
    """Test TargetType enum values."""
    assert TargetType.PROVIDER.value == "provider"
    assert TargetType.TOOL.value == "tool"
    assert TargetType.USER.value == "user"


def test_rate_limit_constraints(test_user: User) -> None:
    """Test RateLimit field constraints."""
    target_id = str(uuid4())

    # Valid constraints should work
    rate_limit = RateLimit(
        id=uuid4(),
        target_type=TargetType.USER,
        target_id=target_id,
        requests_per_window=1,  # Minimum valid value
        window_duration_seconds=1,  # Minimum valid value
        burst_allowance=0,  # Minimum valid value
        current_usage=0,  # Minimum valid value
        created_by=test_user.id,
    )
    assert rate_limit.requests_per_window == 1
    assert rate_limit.window_duration_seconds == 1
    assert rate_limit.burst_allowance == 0
    assert rate_limit.current_usage == 0

    # Zero requests_per_window should be invalid
    with pytest.raises(ValueError):
        RateLimit(
            id=uuid4(),
            target_type=TargetType.USER,
            target_id=target_id,
            requests_per_window=0,  # Should be invalid
            window_duration_seconds=3600,
            created_by=test_user.id,
        )

    # Negative requests_per_window should be invalid
    with pytest.raises(ValueError):
        RateLimit(
            id=uuid4(),
            target_type=TargetType.USER,
            target_id=target_id,
            requests_per_window=-1,  # Should be invalid
            window_duration_seconds=3600,
            created_by=test_user.id,
        )

    # Zero window_duration_seconds should be invalid
    with pytest.raises(ValueError):
        RateLimit(
            id=uuid4(),
            target_type=TargetType.USER,
            target_id=target_id,
            requests_per_window=100,
            window_duration_seconds=0,  # Should be invalid
            created_by=test_user.id,
        )

    # Negative window_duration_seconds should be invalid
    with pytest.raises(ValueError):
        RateLimit(
            id=uuid4(),
            target_type=TargetType.USER,
            target_id=target_id,
            requests_per_window=100,
            window_duration_seconds=-1,  # Should be invalid
            created_by=test_user.id,
        )

    # Negative burst_allowance should be invalid
    with pytest.raises(ValueError):
        RateLimit(
            id=uuid4(),
            target_type=TargetType.USER,
            target_id=target_id,
            requests_per_window=100,
            window_duration_seconds=3600,
            burst_allowance=-1,  # Should be invalid
            created_by=test_user.id,
        )

    # Negative current_usage should be invalid
    with pytest.raises(ValueError):
        RateLimit(
            id=uuid4(),
            target_type=TargetType.USER,
            target_id=target_id,
            requests_per_window=100,
            window_duration_seconds=3600,
            current_usage=-1,  # Should be invalid
            created_by=test_user.id,
        )


@pytest.mark.asyncio
async def test_rate_limit_provider_target(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a rate limit for a provider target."""
    rate_limit_id = uuid4()
    provider_id = str(uuid4())

    rate_limit = RateLimit(
        id=rate_limit_id,
        target_type=TargetType.PROVIDER,
        target_id=provider_id,
        target_name="OpenAI Provider",
        requests_per_window=1000,
        window_duration_seconds=3600,  # 1 hour
        burst_allowance=100,
        created_by=test_user.id,
    )
    test_db_session.add(rate_limit)
    await test_db_session.commit()

    assert rate_limit.target_type == TargetType.PROVIDER
    assert rate_limit.target_id == provider_id
    assert rate_limit.target_name == "OpenAI Provider"
    assert rate_limit.requests_per_window == 1000
    assert rate_limit.burst_allowance == 100


@pytest.mark.asyncio
async def test_rate_limit_tool_target(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a rate limit for a tool target."""
    rate_limit_id = uuid4()
    tool_id = str(uuid4())

    rate_limit = RateLimit(
        id=rate_limit_id,
        target_type=TargetType.TOOL,
        target_id=tool_id,
        target_name="expensive_analysis_tool",
        requests_per_window=10,
        window_duration_seconds=60,  # 1 minute
        burst_allowance=2,
        created_by=test_user.id,
    )
    test_db_session.add(rate_limit)
    await test_db_session.commit()

    assert rate_limit.target_type == TargetType.TOOL
    assert rate_limit.target_id == tool_id
    assert rate_limit.target_name == "expensive_analysis_tool"
    assert rate_limit.requests_per_window == 10
    assert rate_limit.window_duration_seconds == 60
    assert rate_limit.burst_allowance == 2


@pytest.mark.asyncio
async def test_rate_limit_user_target(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a rate limit for a user target."""
    rate_limit_id = uuid4()
    user_id = "user123"  # User targets can be string IDs

    rate_limit = RateLimit(
        id=rate_limit_id,
        target_type=TargetType.USER,
        target_id=user_id,
        target_name="Free Tier User",
        requests_per_window=100,
        window_duration_seconds=86400,  # 24 hours
        burst_allowance=20,
        created_by=test_user.id,
    )
    test_db_session.add(rate_limit)
    await test_db_session.commit()

    assert rate_limit.target_type == TargetType.USER
    assert rate_limit.target_id == user_id
    assert rate_limit.target_name == "Free Tier User"
    assert rate_limit.requests_per_window == 100
    assert rate_limit.window_duration_seconds == 86400
    assert rate_limit.burst_allowance == 20


@pytest.mark.asyncio
async def test_rate_limit_usage_tracking(test_db_session: AsyncSession, test_user: User) -> None:
    """Test rate limit with usage tracking."""
    rate_limit_id = uuid4()
    target_id = str(uuid4())
    now = datetime.now(UTC)
    reset_time = now + timedelta(minutes=5)

    rate_limit = RateLimit(
        id=rate_limit_id,
        target_type=TargetType.TOOL,
        target_id=target_id,
        requests_per_window=50,
        window_duration_seconds=300,  # 5 minutes
        current_usage=35,
        usage_reset_at=reset_time,
        created_by=test_user.id,
    )
    test_db_session.add(rate_limit)
    await test_db_session.commit()

    assert rate_limit.current_usage == 35
    assert rate_limit.usage_reset_at == reset_time

    # Check if limit would be exceeded
    remaining = rate_limit.requests_per_window - rate_limit.current_usage
    assert remaining == 15
