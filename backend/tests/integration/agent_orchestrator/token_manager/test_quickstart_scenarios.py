"""Quickstart validation test for token counting feature.

This test validates all scenarios from quickstart.md to ensure the
implementation matches the specification.
"""

import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.token_manager.exceptions import TokenLimitExceededError
from syntara.agent_orchestrator.token_manager.models import (
    TokenUsageRecord,
    UserTokenConfig,
)
from syntara.agent_orchestrator.token_manager.services import TokenValidationService
from syntara.core.models import User

# Configure logger to output to stdout
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


class TestQuickstartScenarios:
    """Validation tests for quickstart scenarios."""

    @pytest.mark.asyncio
    async def test_scenario_1_request_within_limit(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Scenario 1: Request within limit is accepted."""
        # Create config with 10,000 token limit
        config = UserTokenConfig(user_id=test_user.id, token_limit=10000, window_duration_seconds=86400)
        test_db_session.add(config)
        await test_db_session.commit()

        # Initialize service
        service = TokenValidationService()

        # Simulate 8,000 tokens already used
        usage_record = TokenUsageRecord(user_id=test_user.id, token_count=8000, request_timestamp=datetime.now(UTC))
        test_db_session.add(usage_record)
        await test_db_session.commit()

        # Test: Submit request with ~1,500 tokens
        test_text = "token " * 300  # ~300 words * ~5 tokens/word = ~1500 tokens

        tokens_used = await service.validate_and_record(test_user.id, test_text, test_db_session)
        assert tokens_used > 0, "Should have recorded some tokens"

        # Verify current usage
        usage_stats = await service.get_current_usage(test_user.id, test_db_session)
        current_usage = usage_stats["current_usage"]
        expected = 8000 + tokens_used
        assert current_usage == expected, f"Usage {current_usage} != expected {expected}"
        assert current_usage < 10000, "Should be within limit"

        logger.info("✅ SCENARIO 1 PASSED: %d tokens recorded, total: %d", tokens_used, current_usage)

    @pytest.mark.asyncio
    async def test_scenario_2_request_exceeds_limit(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Scenario 2: Request exceeding limit is blocked."""
        # Create config
        config = UserTokenConfig(user_id=test_user.id, token_limit=10000, window_duration_seconds=86400)
        test_db_session.add(config)
        await test_db_session.commit()

        # Initialize service
        service = TokenValidationService()

        # Simulate 9,500 tokens already used
        usage_record = TokenUsageRecord(user_id=test_user.id, token_count=9500, request_timestamp=datetime.now(UTC))
        test_db_session.add(usage_record)
        await test_db_session.commit()

        # Test: Submit request that would exceed limit
        # Need enough tokens to exceed: limit=10000, current=9500, so need >500 tokens
        # "token " is ~1 token, so use 600 repetitions to ensure we exceed
        large_text = "token " * 600  # ~600 tokens, which will push total to ~10100

        with pytest.raises(TokenLimitExceededError) as exc_info:
            await service.validate_and_record(test_user.id, large_text, test_db_session)

        # Verify error details
        error = exc_info.value
        assert error.current_usage == 9500
        assert error.token_limit == 10000
        assert error.request_tokens > 0

        # Verify usage wasn't recorded
        usage_stats = await service.get_current_usage(test_user.id, test_db_session)
        final_usage = usage_stats["current_usage"]
        assert final_usage == 9500, "Usage should not have increased"

        logger.info("✅ SCENARIO 2 PASSED: Request correctly blocked at %d/%d", error.current_usage, error.token_limit)

    @pytest.mark.asyncio
    async def test_scenario_3_rolling_window_excludes_old_records(
        self, test_db_session: AsyncSession, user_factory: Callable[..., Awaitable[User]]
    ) -> None:
        """Scenario 3: Rolling window excludes old records."""
        # Create test user
        user = await user_factory(
            username="qs_user3",
            email="qs_user3@example.com",
            first_name="Quickstart",
            last_name="User 3",
        )

        # Create config with 24-hour window
        config = UserTokenConfig(user_id=user.id, token_limit=10000, window_duration_seconds=86400)
        test_db_session.add(config)
        await test_db_session.commit()

        # Create old usage record (25 hours ago = 90,000 seconds)
        old_timestamp = datetime.now(UTC) - timedelta(seconds=90000)
        old_record = TokenUsageRecord(user_id=user.id, token_count=5000, request_timestamp=old_timestamp)
        test_db_session.add(old_record)

        # Create recent usage record (12 hours ago)
        recent_timestamp = datetime.now(UTC) - timedelta(hours=12)
        recent_record = TokenUsageRecord(user_id=user.id, token_count=3000, request_timestamp=recent_timestamp)
        test_db_session.add(recent_record)
        await test_db_session.commit()

        # Initialize service
        service = TokenValidationService()

        # Test: Current usage should only include recent record
        usage_stats = await service.get_current_usage(user.id, test_db_session)
        current_usage = usage_stats["current_usage"]
        assert current_usage == 3000, f"Expected 3000 (old record excluded), got {current_usage}"

        # Test: New request should be validated against only recent usage
        test_text = "token " * 200
        tokens_used = await service.validate_and_record(user.id, test_text, test_db_session)
        new_usage_stats = await service.get_current_usage(user.id, test_db_session)
        new_usage = new_usage_stats["current_usage"]

        expected = 3000 + tokens_used
        assert new_usage == expected, f"Expected {expected}, got {new_usage}"

        logger.info("✅ SCENARIO 3 PASSED: Rolling window correctly excluded old records, new total: %d", new_usage)

    @pytest.mark.asyncio
    async def test_scenario_4_per_user_independence(
        self, test_db_session: AsyncSession, user_factory: Callable[..., Awaitable[User]]
    ) -> None:
        """Scenario 4: Per-user independence."""
        # Create two test users
        user_a = await user_factory(
            username="qs_user_a",
            email="qs_user_a@example.com",
            first_name="Quickstart",
            last_name="User A",
        )
        user_b = await user_factory(
            username="qs_user_b",
            email="qs_user_b@example.com",
            first_name="Quickstart",
            last_name="User B",
        )

        # Create different configs
        config_a = UserTokenConfig(user_id=user_a.id, token_limit=5000, window_duration_seconds=3600)
        config_b = UserTokenConfig(user_id=user_b.id, token_limit=10000, window_duration_seconds=86400)
        test_db_session.add_all([config_a, config_b])
        await test_db_session.commit()

        # Initialize service
        service = TokenValidationService()

        # User A uses 4,500 tokens
        usage_a = TokenUsageRecord(user_id=user_a.id, token_count=4500, request_timestamp=datetime.now(UTC))
        test_db_session.add(usage_a)

        # User B uses 9,000 tokens
        usage_b = TokenUsageRecord(user_id=user_b.id, token_count=9000, request_timestamp=datetime.now(UTC))
        test_db_session.add(usage_b)
        await test_db_session.commit()

        # Verify independent tracking
        usage_a_stats = await service.get_current_usage(user_a.id, test_db_session)
        usage_b_stats = await service.get_current_usage(user_b.id, test_db_session)
        usage_a_val = usage_a_stats["current_usage"]
        usage_b_val = usage_b_stats["current_usage"]

        assert usage_a_val == 4500
        assert usage_b_val == 9000

        # User A can't exceed their limit (has 4500/5000, so needs >500 tokens to exceed)
        with pytest.raises(TokenLimitExceededError):
            await service.validate_and_record(
                user_a.id,
                "token " * 600,
                test_db_session,  # ~600 tokens exceeds limit
            )

        # User B still has budget
        tokens_b = await service.validate_and_record(user_b.id, "token " * 100, test_db_session)
        assert tokens_b > 0, "User B should have been accepted"

        logger.info("✅ SCENARIO 4 PASSED: Users tracked independently (A: %d, B: %d)", usage_a_val, usage_b_val)
