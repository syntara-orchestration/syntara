"""Integration tests for token validation flow.

These tests cover end-to-end scenarios from the specification:
- T009: Request within limit accepted
- T010: Request exceeding limit blocked
- T013: Per-user independence
- T023: Budget uses actual token_count for completed invocations
"""

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.token_manager.exceptions import TokenLimitExceededError
from syntara.agent_orchestrator.token_manager.models import UserTokenConfig
from syntara.agent_orchestrator.token_manager.repository import TokenUsageRepository
from syntara.agent_orchestrator.token_manager.services import TokenValidationService


@pytest_asyncio.fixture
async def user_a_config(test_db_session: AsyncSession, test_user) -> UserTokenConfig:
    """Create configuration for user A."""
    config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=10000,
        window_duration_seconds=3600,  # 1 hour
    )
    test_db_session.add(config)
    await test_db_session.commit()
    return config


@pytest_asyncio.fixture
async def user_b_config(test_db_session: AsyncSession, user_factory) -> UserTokenConfig:
    """Create configuration for user B."""
    user_b = await user_factory(
        email="userb@example.com",
        username="userb",
        first_name="User",
        last_name="B",
    )

    config = UserTokenConfig(
        user_id=user_b.id,
        token_limit=5000,
        window_duration_seconds=3600,  # 1 hour
    )
    test_db_session.add(config)
    await test_db_session.commit()
    return config


@pytest.fixture
def service() -> TokenValidationService:
    """Create TokenValidationService."""
    return TokenValidationService()


@pytest.mark.asyncio
async def test_request_within_limit_accepted(
    service: TokenValidationService,
    user_a_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test T009: Request within limit is accepted and usage updated.

    Scenario 1 from spec:
    Given a user's cumulative token count is at 8,000 and their configured limit is 10,000,
    When that user submits a new request with ~1,500 tokens,
    Then the system should accept the request and update the user's cumulative count to ~9,500
    """
    # Arrange: Create existing usage of 8000 tokens
    text_8000 = " ".join(["word"] * 8000)  # 8000 tokens (1 token per word)
    await service.validate_and_record(
        user_id=user_a_config.user_id,
        request_text=text_8000,
        session=test_db_session,
    )
    await test_db_session.commit()

    # Verify current usage is ~8000
    usage_stats = await service.get_current_usage(
        user_id=user_a_config.user_id,
        session=test_db_session,
    )
    assert 7800 <= usage_stats["current_usage"] <= 8200

    # Act: Submit request with ~1500 tokens
    text_1500 = " ".join(["word"] * 1500)  # 1500 tokens
    tokens = await service.validate_and_record(
        user_id=user_a_config.user_id,
        request_text=text_1500,
        session=test_db_session,
    )
    await test_db_session.commit()

    # Assert: Request accepted and usage updated
    assert 1400 <= tokens <= 1600
    final_usage = await service.get_current_usage(
        user_id=user_a_config.user_id,
        session=test_db_session,
    )
    assert 9200 <= final_usage["current_usage"] <= 9800


@pytest.mark.asyncio
async def test_request_exceeding_limit_blocked(
    service: TokenValidationService,
    user_a_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test T010: Request exceeding limit raises TokenLimitExceededError.

    Scenario 2 from spec:
    Given a user's cumulative token count is at 9,500 and their configured limit is 10,000,
    When that user submits a request with ~1,000 tokens,
    Then the system should block the request with TokenLimitExceededError
    """
    # Arrange: Create existing usage of ~9500 tokens
    text_9500 = " ".join(["word"] * 9500)  # 9500 tokens
    await service.validate_and_record(
        user_id=user_a_config.user_id,
        request_text=text_9500,
        session=test_db_session,
    )
    await test_db_session.commit()

    # Verify current usage
    usage_stats = await service.get_current_usage(
        user_id=user_a_config.user_id,
        session=test_db_session,
    )
    assert 9300 <= usage_stats["current_usage"] <= 9700

    # Act & Assert: Request with ~1000 tokens should be blocked
    text_1000 = " ".join(["word"] * 1000)  # 1000 tokens
    user_id = user_a_config.user_id  # Store user_id before rollback
    with pytest.raises(TokenLimitExceededError) as exc_info:
        await service.validate_and_record(
            user_id=user_id,
            request_text=text_1000,
            session=test_db_session,
        )

    # Verify error details
    error = exc_info.value
    assert error.user_id == user_id
    assert 9300 <= error.current_usage <= 9700
    assert error.token_limit == 10000
    assert 900 <= error.request_tokens <= 1100
    assert error.current_usage + error.request_tokens > error.token_limit

    # Verify usage was NOT recorded (transaction rolled back)
    await test_db_session.rollback()
    final_usage = await service.get_current_usage(
        user_id=user_id,
        session=test_db_session,
    )
    # Usage should be unchanged
    assert 9300 <= final_usage["current_usage"] <= 9700


@pytest.mark.asyncio
async def test_per_user_independence(
    service: TokenValidationService,
    user_a_config: UserTokenConfig,
    user_b_config: UserTokenConfig,
    test_db_session: AsyncSession,
) -> None:
    """Test T013: Each user's token budget is tracked independently.

    Scenario 5 from spec:
    Given multiple users are making requests,
    When tracking token counts,
    Then each user's cumulative count should be tracked independently
    """
    # Arrange: User A uses 4500 tokens (limit: 10000)
    text_a_4500 = " ".join(["word"] * 4500)  # 4500 tokens
    await service.validate_and_record(
        user_id=user_a_config.user_id,
        request_text=text_a_4500,
        session=test_db_session,
    )

    # Arrange: User B uses 4500 tokens (limit: 5000)
    text_b_4500 = " ".join(["word"] * 4500)  # 4500 tokens
    await service.validate_and_record(
        user_id=user_b_config.user_id,
        request_text=text_b_4500,
        session=test_db_session,
    )
    await test_db_session.commit()

    # Verify independent tracking
    usage_a = await service.get_current_usage(
        user_id=user_a_config.user_id,
        session=test_db_session,
    )
    usage_b = await service.get_current_usage(
        user_id=user_b_config.user_id,
        session=test_db_session,
    )

    assert 4300 <= usage_a["current_usage"] <= 4700
    assert usage_a["token_limit"] == 10000
    assert usage_a["remaining"] >= 5300

    assert 4300 <= usage_b["current_usage"] <= 4700
    assert usage_b["token_limit"] == 5000
    assert usage_b["remaining"] <= 700

    # User A can still make requests (has budget remaining)
    text_a_1000 = " ".join(["word"] * 1000)
    tokens_a = await service.validate_and_record(
        user_id=user_a_config.user_id,
        request_text=text_a_1000,
        session=test_db_session,
    )
    await test_db_session.commit()
    assert 900 <= tokens_a <= 1100

    # User B should be blocked (near limit)
    text_b_1000 = " ".join(["word"] * 1000)
    user_id_a = user_a_config.user_id  # Store user IDs before rollback
    user_id_b = user_b_config.user_id
    with pytest.raises(TokenLimitExceededError):
        await service.validate_and_record(
            user_id=user_id_b,
            request_text=text_b_1000,
            session=test_db_session,
        )

    # Verify final states
    await test_db_session.rollback()
    final_usage_a = await service.get_current_usage(
        user_id=user_id_a,
        session=test_db_session,
    )
    final_usage_b = await service.get_current_usage(
        user_id=user_id_b,
        session=test_db_session,
    )

    # User A should have increased usage
    assert 5200 <= final_usage_a["current_usage"] <= 5800

    # User B should have unchanged usage (request blocked)
    assert 4300 <= final_usage_b["current_usage"] <= 4700


# T023: Budget uses actual token_count for completed invocations


@pytest.mark.asyncio
async def test_budget_reflects_actual_tokens_after_update(
    service: TokenValidationService,
    user_a_config: UserTokenConfig,
    test_db_session: AsyncSession,
    test_user,
    test_project_id,
) -> None:
    """US1-S2/US3-S3: Budget uses actual token_count for completed invocations.

    When a record is updated with actual tokens (lower than estimate),
    the budget should reflect the actual total, freeing up capacity.
    """
    from syntara.agent_orchestrator.models import Invocation, InvocationStatus

    # Create an invocation
    invocation = Invocation(
        prompt="test prompt",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-001",
        status=InvocationStatus.RUNNING,
    )
    test_db_session.add(invocation)
    await test_db_session.flush()

    # Record usage with estimate of 5000 tokens
    text_5000 = " ".join(["word"] * 5000)
    await service.validate_and_record(
        user_id=user_a_config.user_id,
        request_text=text_5000,
        session=test_db_session,
        invocation_id=invocation.id,
    )
    await test_db_session.commit()

    # Verify initial budget includes the estimate
    usage_before = await service.get_current_usage(
        user_id=user_a_config.user_id,
        session=test_db_session,
    )
    assert 4800 <= usage_before["current_usage"] <= 5200

    # Simulate post-LLM update with LOWER actual tokens
    repo = TokenUsageRepository()
    await repo.update_with_actual_token_usage(
        invocation_id=invocation.id,
        prompt_tokens=2000,
        completion_tokens=500,
        token_count=2500,  # Much less than the ~5000 estimate
        usage_details=[{"prompt_tokens": 2000, "completion_tokens": 500}],
        session=test_db_session,
    )
    await test_db_session.commit()

    # Budget should now reflect actual total (2500), not estimate (~5000)
    usage_after = await service.get_current_usage(
        user_id=user_a_config.user_id,
        session=test_db_session,
    )
    assert 2300 <= usage_after["current_usage"] <= 2700
    # User should have more remaining capacity now
    assert usage_after["remaining"] > usage_before["remaining"]
