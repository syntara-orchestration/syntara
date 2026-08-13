"""Integration tests for concurrent request handling.

Tests T012: Concurrent requests are handled safely without race conditions.
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.token_manager.exceptions import TokenLimitExceededError
from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord, UserTokenConfig
from syntara.agent_orchestrator.token_manager.services import TokenValidationService


@pytest_asyncio.fixture
async def user_config(test_db_session: AsyncSession, test_user) -> UserTokenConfig:
    """Create test user configuration."""
    config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=10000,
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
async def test_concurrent_requests_accurate_counting(
    service: TokenValidationService,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
    test_db_engine: AsyncEngine,
) -> None:
    """Test T012: Concurrent requests are counted accurately without race conditions.

    Scenario 4 from spec:
    Given multiple requests arrive simultaneously from the same user,
    When processing token counts,
    Then the system should accurately track cumulative totals without
    double-counting or missing requests.

    Verification:
    - SELECT FOR UPDATE row-level locking prevents race conditions
    - Atomicity: Sum of recorded usage == final cumulative count
    - Over-limit prevention: Final usage never exceeds token_limit
    """
    # Arrange: Create 10 concurrent requests of ~500 tokens each
    num_requests = 10
    text_500 = " ".join(["word"] * 500)  # 500 tokens

    async def submit_request(session: AsyncSession, request_num: int) -> tuple[int, bool]:
        """Submit a single request and return (request_num, success)."""
        try:
            await service.validate_and_record(
                user_id=user_config.user_id,
                request_text=text_500,
                session=session,
            )
            await session.commit()
            return (request_num, True)
        except TokenLimitExceededError:
            await session.rollback()
            return (request_num, False)

    # Act: Submit requests concurrently
    # Note: Each request needs its own session for proper transaction isolation
    async_session_factory = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    tasks = []
    for i in range(num_requests):

        async def run_request(req_num: int) -> tuple[int, bool]:
            async with async_session_factory() as session:
                return await submit_request(session, req_num)

        tasks.append(run_request(i))

    results = await asyncio.gather(*tasks)

    # Assert: Verify results
    successful_requests = [r for r, success in results if success]

    # Calculate expected outcomes
    # With limit=10000 and ~500 tokens/request, we should accept ~19-20 requests
    # But we're only sending 10, so most should succeed

    # Verify final usage doesn't exceed limit
    async with async_session_factory() as session:
        final_usage = await service.get_current_usage(
            user_id=user_config.user_id,
            session=session,
        )

    assert final_usage["current_usage"] <= 10000, "Usage must not exceed limit"

    # Verify all successful requests were recorded
    async with async_session_factory() as session:
        result = await session.exec(select(TokenUsageRecord).where(TokenUsageRecord.user_id == user_config.user_id))
        records = result.all()

    assert len(records) == len(successful_requests), "All successful requests must be recorded"

    # Verify atomicity: sum of all records == current usage
    total_from_records = sum(record.token_count for record in records)
    assert total_from_records == final_usage["current_usage"], "Sum of records must equal current usage"

    # Verify no double-counting: each request recorded exactly once
    assert len(records) <= num_requests, "No request should be recorded more than once"


@pytest.mark.asyncio
async def test_concurrent_requests_near_limit(
    service: TokenValidationService,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
    test_db_engine: AsyncEngine,
) -> None:
    """Test concurrent requests when close to the limit.

    This tests the edge case where multiple requests could push over the limit,
    ensuring that row-level locking prevents race conditions.
    """
    # Arrange: Set usage close to limit
    text_9000 = " ".join(["word"] * 9000)  # 9000 tokens
    await service.validate_and_record(
        user_id=user_config.user_id,
        request_text=text_9000,
        session=test_db_session,
    )
    await test_db_session.commit()

    # Act: Submit 5 concurrent requests of ~500 tokens each
    # Only 2 should succeed (bringing total to ~10000), rest should be blocked
    num_requests = 5
    text_500 = " ".join(["word"] * 500)

    async def submit_request(session: AsyncSession, request_num: int) -> tuple[int, bool]:
        try:
            await service.validate_and_record(
                user_id=user_config.user_id,
                request_text=text_500,
                session=session,
            )
            await session.commit()
            return (request_num, True)
        except TokenLimitExceededError:
            await session.rollback()
            return (request_num, False)

    async_session_factory = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    tasks = []
    for i in range(num_requests):

        async def run_request(req_num: int) -> tuple[int, bool]:
            async with async_session_factory() as session:
                return await submit_request(session, req_num)

        tasks.append(run_request(i))

    results = await asyncio.gather(*tasks)

    failed_requests = [r for r, success in results if not success]

    # Assert: At least some requests should be blocked
    assert len(failed_requests) >= 1, "Some requests should be blocked when near limit"

    # Verify final usage doesn't exceed limit
    async with async_session_factory() as session:
        final_usage = await service.get_current_usage(
            user_id=user_config.user_id,
            session=session,
        )

    assert final_usage["current_usage"] <= 10000, "Usage must never exceed limit"


@pytest.mark.asyncio
async def test_row_level_locking_prevents_race_condition(
    service: TokenValidationService,
    user_config: UserTokenConfig,
    test_db_session: AsyncSession,
    test_db_engine: AsyncEngine,
) -> None:
    """Test that SELECT FOR UPDATE locking is actually used.

    This is a smoke test to ensure the implementation uses row-level locking.
    The test verifies that concurrent requests block each other rather than
    all reading the same value simultaneously.
    """
    # Arrange: Start with 5000 tokens used
    text_5000 = " ".join(["word"] * 5000)
    await service.validate_and_record(
        user_id=user_config.user_id,
        request_text=text_5000,
        session=test_db_session,
    )
    await test_db_session.commit()

    # Act: Submit 10 concurrent requests of ~1000 tokens each
    # With locking: requests execute serially within transaction, some succeed, some fail
    # Without locking: all might read 5000, all try to add 1000, race condition
    num_requests = 10
    text_1000 = " ".join(["word"] * 1000)

    async def submit_request(session: AsyncSession) -> bool:
        try:
            await service.validate_and_record(
                user_id=user_config.user_id,
                request_text=text_1000,
                session=session,
            )
            await session.commit()
            return True
        except TokenLimitExceededError:
            await session.rollback()
            return False

    async_session_factory = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    tasks = []
    for _ in range(num_requests):

        async def run_request() -> bool:
            async with async_session_factory() as session:
                return await submit_request(session)

        tasks.append(run_request())

    results = await asyncio.gather(*tasks)

    successful_count = sum(1 for r in results if r)
    failed_count = sum(1 for r in results if not r)

    # Assert: With locking, we should have a mix of success/failure
    # Expected: ~4-5 successful (to reach ~10000), ~5-6 failed
    assert successful_count >= 3, "Some requests should succeed"
    assert failed_count >= 3, "Some requests should be blocked"

    # Verify final usage is consistent and doesn't exceed limit
    async with async_session_factory() as session:
        final_usage = await service.get_current_usage(
            user_id=user_config.user_id,
            session=session,
        )

    assert final_usage["current_usage"] <= 10000
    assert final_usage["current_usage"] >= 8000  # At least a few succeeded
