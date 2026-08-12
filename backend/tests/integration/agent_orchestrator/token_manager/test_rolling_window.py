"""Integration tests for rolling window behavior.

Tests T011: Rolling window correctly includes/excludes records based on time.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord, UserTokenConfig
from syntara.agent_orchestrator.token_manager.services import TokenValidationService
from syntara.core.models import User


@pytest_asyncio.fixture
async def user_config(test_db_session: AsyncSession, test_user) -> UserTokenConfig:
    """Create test user configuration with 1-hour rolling window."""
    config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=10000,
        window_duration_seconds=3600,  # 1 hour window
    )
    test_db_session.add(config)
    await test_db_session.commit()
    return config


@pytest.fixture
def service() -> TokenValidationService:
    """Create TokenValidationService."""
    return TokenValidationService()


@pytest.mark.asyncio
async def test_rolling_window_excludes_old_requests(
    service: TokenValidationService,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test T011: Old records outside the window are excluded from usage calculation.

    Scenario 6 from spec:
    Given a user made a request 90,000 seconds ago (25 hours)
    and their rolling window is 86,400 seconds (24 hours),
    When calculating current usage,
    Then the 90,000-second-old request should be excluded
    """
    # Arrange: Create an old record (2 hours ago - outside 1 hour window)
    now = datetime.now(UTC)
    old_record = TokenUsageRecord(
        user_id=user_config.user_id,
        token_count=5000,
        request_timestamp=now - timedelta(hours=2),  # 7200 seconds ago
    )
    test_db_session.add(old_record)

    # Create a recent record (30 minutes ago - inside 1 hour window)
    recent_record = TokenUsageRecord(
        user_id=user_config.user_id,
        token_count=3000,
        request_timestamp=now - timedelta(minutes=30),  # 1800 seconds ago
    )
    test_db_session.add(recent_record)
    await test_db_session.commit()

    # Act: Get current usage (should only include recent record)
    usage_stats = await service.get_current_usage(
        user_id=user_config.user_id,
        session=test_db_session,
    )

    # Assert: Only recent record counted (old one excluded)
    assert usage_stats["current_usage"] == 3000
    assert usage_stats["remaining"] == 7000


@pytest.mark.asyncio
async def test_rolling_window_includes_recent_requests(
    service: TokenValidationService,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test T011: All records within the window are included.

    Scenario 7 from spec:
    Given a user's requests are all within their configured rolling window,
    When calculating cumulative usage,
    Then all requests within the window should be counted toward their limit
    """
    # Arrange: Create multiple records within the 1-hour window
    now = datetime.now(UTC)
    records = [
        TokenUsageRecord(
            user_id=user_config.user_id,
            token_count=2000,
            request_timestamp=now - timedelta(minutes=50),
        ),
        TokenUsageRecord(
            user_id=user_config.user_id,
            token_count=1500,
            request_timestamp=now - timedelta(minutes=40),
        ),
        TokenUsageRecord(
            user_id=user_config.user_id,
            token_count=2500,
            request_timestamp=now - timedelta(minutes=20),
        ),
        TokenUsageRecord(
            user_id=user_config.user_id,
            token_count=1000,
            request_timestamp=now - timedelta(minutes=5),
        ),
    ]
    for record in records:
        test_db_session.add(record)
    await test_db_session.commit()

    # Act: Get current usage
    usage_stats = await service.get_current_usage(
        user_id=user_config.user_id,
        session=test_db_session,
    )

    # Assert: All records within window are counted
    assert usage_stats["current_usage"] == 7000  # 2000 + 1500 + 2500 + 1000
    assert usage_stats["remaining"] == 3000


@pytest.mark.asyncio
async def test_per_user_window_configuration(
    service: TokenValidationService,
    test_db_session: AsyncSession,
    test_user,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Test T011: Each user can have a different rolling window duration.

    Scenario 8 from spec:
    Given different users have different rolling window configurations,
    When calculating token usage,
    Then each user's cumulative count should be calculated using their own window duration
    """
    # Arrange: User A with 1-hour window
    user_a_config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=10000,
        window_duration_seconds=3600,  # 1 hour
    )
    test_db_session.add(user_a_config)

    # User B with 24-hour window
    user_b = await user_factory(
        email="userb_window@example.com",
        username="userb_window",
        first_name="User B",
        last_name="Window",
    )

    user_b_config = UserTokenConfig(
        user_id=user_b.id,
        token_limit=20000,
        window_duration_seconds=86400,  # 24 hours
    )
    test_db_session.add(user_b_config)
    await test_db_session.commit()

    # Create records for both users from 2 hours ago
    now = datetime.now(UTC)
    timestamp_2h_ago = now - timedelta(hours=2)

    record_a = TokenUsageRecord(
        user_id=user_a_config.user_id,
        token_count=4000,
        request_timestamp=timestamp_2h_ago,
    )
    record_b = TokenUsageRecord(
        user_id=user_b_config.user_id,
        token_count=4000,
        request_timestamp=timestamp_2h_ago,
    )
    test_db_session.add(record_a)
    test_db_session.add(record_b)
    await test_db_session.commit()

    # Act: Get usage for both users
    usage_a = await service.get_current_usage(
        user_id=user_a_config.user_id,
        session=test_db_session,
    )
    usage_b = await service.get_current_usage(
        user_id=user_b_config.user_id,
        session=test_db_session,
    )

    # Assert:
    # User A: 2 hours ago is outside 1-hour window -> usage = 0
    assert usage_a["current_usage"] == 0
    assert usage_a["window_duration_seconds"] == 3600

    # User B: 2 hours ago is inside 24-hour window -> usage = 4000
    assert usage_b["current_usage"] == 4000
    assert usage_b["window_duration_seconds"] == 86400


@pytest.mark.asyncio
async def test_rolling_window_with_new_request(
    service: TokenValidationService,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test that new requests work correctly with rolling window calculations."""
    # Arrange: Create old record (outside window) and recent record (inside window)
    now = datetime.now(UTC)
    old_record = TokenUsageRecord(
        user_id=user_config.user_id,
        token_count=6000,
        request_timestamp=now - timedelta(hours=2),
    )
    recent_record = TokenUsageRecord(
        user_id=user_config.user_id,
        token_count=2000,
        request_timestamp=now - timedelta(minutes=30),
    )
    test_db_session.add(old_record)
    test_db_session.add(recent_record)
    await test_db_session.commit()

    # Act: Submit new request with ~3000 tokens
    text_3000 = " ".join(["word"] * 3000)  # 3000 words = ~3000 tokens
    tokens = await service.validate_and_record(
        user_id=user_config.user_id,
        request_text=text_3000,
        session=test_db_session,
    )
    await test_db_session.commit()

    # Assert: Request accepted (current usage ~2000 + 3000 = ~5000, limit = 10000)
    assert 2900 <= tokens <= 3100  # Allow small variance

    # Verify final usage only includes recent records (not the old one)
    final_usage = await service.get_current_usage(
        user_id=user_config.user_id,
        session=test_db_session,
    )
    # Should be ~2000 (recent) + ~3000 (new) = ~5000
    assert 4800 <= final_usage["current_usage"] <= 5200
