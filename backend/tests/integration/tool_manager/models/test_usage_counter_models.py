"""Unit tests for UsageCounter models.

Tests cover:
- UsageCounter creation with required fields
- CounterType and WindowDuration enums
- Field validation and constraints
- Foreign key relationships
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration
from syntara.tool_manager.models import Tool
from syntara.tool_manager.models.usage_counter import (
    CounterType,
    UsageCounter,
    WindowDuration,
)


@pytest.mark.asyncio
async def test_create_usage_counter_with_required_fields(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a usage counter with all required fields."""
    counter_id = uuid4()
    now = datetime.now(UTC)
    window_end = now + timedelta(hours=1)

    counter = UsageCounter(
        id=counter_id,
        counter_type=CounterType.TOOL,
        time_window="2025-01-01-14",
        window_duration=WindowDuration.HOUR,
        window_start=now,
        window_end=window_end,
        created_by=test_user.id,
    )
    test_db_session.add(counter)
    await test_db_session.commit()

    assert counter.id == counter_id
    assert counter.counter_type == CounterType.TOOL
    assert counter.tool_id is None  # Default value
    assert counter.user_id is None  # Default value
    assert counter.time_window == "2025-01-01-14"
    assert counter.window_duration == WindowDuration.HOUR
    assert counter.request_count == 0  # Default value
    assert counter.success_count == 0  # Default value
    assert counter.error_count == 0  # Default value
    assert counter.total_duration_ms == 0  # Default value
    assert counter.window_start == now
    assert counter.window_end == window_end
    assert counter.created_by == test_user.id
    assert counter.created_at is not None
    assert counter.updated_at is not None


@pytest.mark.asyncio
async def test_create_usage_counter_with_all_fields(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test creating a usage counter with all fields including optional ones."""
    counter_id = uuid4()
    now = datetime.now(UTC)
    window_end = now + timedelta(days=1)

    counter = UsageCounter(
        id=counter_id,
        counter_type=CounterType.TOOL_USER,
        tool_id=test_tool.id,
        user_id=test_user.id,
        time_window="2025-01-01",
        window_duration=WindowDuration.DAY,
        request_count=100,
        success_count=85,
        error_count=15,
        total_duration_ms=120000,
        window_start=now,
        window_end=window_end,
        created_by=test_user.id,
        labels={"env": "production", "region": "us-east-1"},
    )
    test_db_session.add(counter)
    await test_db_session.commit()

    assert counter.counter_type == CounterType.TOOL_USER
    assert counter.tool_id == test_tool.id
    assert counter.user_id == test_user.id
    assert counter.time_window == "2025-01-01"
    assert counter.window_duration == WindowDuration.DAY
    assert counter.request_count == 100
    assert counter.success_count == 85
    assert counter.error_count == 15
    assert counter.total_duration_ms == 120000
    assert counter.labels == {"env": "production", "region": "us-east-1"}


def test_counter_type_enum() -> None:
    """Test CounterType enum values."""
    assert CounterType.PROVIDER.value == "provider"
    assert CounterType.TOOL.value == "tool"
    assert CounterType.USER.value == "user"
    assert CounterType.PROVIDER_USER.value == "provider_user"
    assert CounterType.TOOL_USER.value == "tool_user"


def test_window_duration_enum() -> None:
    """Test WindowDuration enum values."""
    assert WindowDuration.HOUR.value == "hour"
    assert WindowDuration.DAY.value == "day"
    assert WindowDuration.MONTH.value == "month"


def test_usage_counter_constraints(test_user: User) -> None:
    """Test UsageCounter field constraints."""
    now = datetime.now(UTC)
    window_end = now + timedelta(hours=1)

    # Valid counts (>= 0) should work
    counter = UsageCounter(
        id=uuid4(),
        counter_type=CounterType.TOOL,
        time_window="2025-01-01-14",
        window_duration=WindowDuration.HOUR,
        request_count=0,  # Should be valid
        success_count=0,  # Should be valid
        error_count=0,  # Should be valid
        total_duration_ms=0,  # Should be valid
        window_start=now,
        window_end=window_end,
        created_by=test_user.id,
    )
    assert counter.request_count == 0
    assert counter.success_count == 0
    assert counter.error_count == 0
    assert counter.total_duration_ms == 0

    # Negative request_count should be invalid
    with pytest.raises(ValueError):
        UsageCounter(
            id=uuid4(),
            counter_type=CounterType.TOOL,
            time_window="2025-01-01-14",
            window_duration=WindowDuration.HOUR,
            request_count=-1,  # Should be invalid
            window_start=now,
            window_end=window_end,
            created_by=test_user.id,
        )

    # Negative success_count should be invalid
    with pytest.raises(ValueError):
        UsageCounter(
            id=uuid4(),
            counter_type=CounterType.TOOL,
            time_window="2025-01-01-14",
            window_duration=WindowDuration.HOUR,
            success_count=-1,  # Should be invalid
            window_start=now,
            window_end=window_end,
            created_by=test_user.id,
        )

    # Negative error_count should be invalid
    with pytest.raises(ValueError):
        UsageCounter(
            id=uuid4(),
            counter_type=CounterType.TOOL,
            time_window="2025-01-01-14",
            window_duration=WindowDuration.HOUR,
            error_count=-1,  # Should be invalid
            window_start=now,
            window_end=window_end,
            created_by=test_user.id,
        )

    # Negative total_duration_ms should be invalid
    with pytest.raises(ValueError):
        UsageCounter(
            id=uuid4(),
            counter_type=CounterType.TOOL,
            time_window="2025-01-01-14",
            window_duration=WindowDuration.HOUR,
            total_duration_ms=-1,  # Should be invalid
            window_start=now,
            window_end=window_end,
            created_by=test_user.id,
        )


@pytest.mark.asyncio
async def test_usage_counter_tool_scoped(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test creating a tool-scoped usage counter."""
    counter_id = uuid4()
    now = datetime.now(UTC)
    window_end = now + timedelta(days=1)

    counter = UsageCounter(
        id=counter_id,
        counter_type=CounterType.TOOL,
        tool_id=test_tool.id,
        time_window="2025-01-01",
        window_duration=WindowDuration.DAY,
        request_count=200,
        success_count=180,
        error_count=20,
        window_start=now,
        window_end=window_end,
        created_by=test_user.id,
    )
    test_db_session.add(counter)
    await test_db_session.commit()

    assert counter.counter_type == CounterType.TOOL
    assert counter.tool_id == test_tool.id
    assert counter.user_id is None


@pytest.mark.asyncio
async def test_usage_counter_user_scoped(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a user-scoped usage counter."""
    counter_id = uuid4()
    now = datetime.now(UTC)
    window_end = now + timedelta(days=30)

    counter = UsageCounter(
        id=counter_id,
        counter_type=CounterType.USER,
        user_id=test_user.id,
        time_window="2025-01",
        window_duration=WindowDuration.MONTH,
        request_count=1000,
        success_count=950,
        error_count=50,
        total_duration_ms=3600000,  # 1 hour total
        window_start=now,
        window_end=window_end,
        created_by=test_user.id,
    )
    test_db_session.add(counter)
    await test_db_session.commit()

    assert counter.counter_type == CounterType.USER
    assert counter.tool_id is None
    assert counter.user_id == test_user.id
    assert counter.window_duration == WindowDuration.MONTH


@pytest.mark.asyncio
async def test_usage_counter_integration_scoped(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> None:
    """Test creating an integration-scoped usage counter."""
    counter_id = uuid4()
    now = datetime.now(UTC)
    window_end = now + timedelta(hours=1)

    counter = UsageCounter(
        id=counter_id,
        counter_type=CounterType.PROVIDER,
        integration_id=test_mcp_integration.id,
        time_window="2025-01-01-14",
        window_duration=WindowDuration.HOUR,
        request_count=50,
        success_count=45,
        error_count=5,
        window_start=now,
        window_end=window_end,
        created_by=test_user.id,
    )
    test_db_session.add(counter)
    await test_db_session.commit()

    assert counter.counter_type == CounterType.PROVIDER
    assert counter.integration_id == test_mcp_integration.id
    assert counter.tool_id is None
    assert counter.user_id is None
