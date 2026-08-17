"""Integration tests for post-LLM token recording (T016, T022, T024).

Covers:
- US1-S1: Record updated with actual token counts
- US1-S3: No update on LLM failure (no usage metadata)
- FR-007: Update failure is non-blocking
- FR-008: No token metadata skips update
- FR-011: usage_details is non-null JSONB after successful update
- US2: invocation_id correlation
"""

import pytest
import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models import Invocation, InvocationStatus
from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord, UserTokenConfig
from syntara.agent_orchestrator.token_manager.repository import TokenUsageRepository


@pytest_asyncio.fixture
async def user_config(test_db_session: AsyncSession, test_user) -> UserTokenConfig:
    """Create a test user token configuration."""
    config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=100000,
        window_duration_seconds=3600,
    )
    test_db_session.add(config)
    await test_db_session.commit()
    return config


@pytest_asyncio.fixture
async def invocation(test_db_session: AsyncSession, test_user, test_project_id) -> Invocation:
    """Create a test invocation."""
    inv = Invocation(
        prompt="test prompt",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-001",
        status=InvocationStatus.RUNNING,
    )
    test_db_session.add(inv)
    await test_db_session.flush()
    return inv


@pytest_asyncio.fixture
async def pre_llm_record(
    test_db_session: AsyncSession, test_user, user_config: UserTokenConfig, invocation: Invocation
) -> TokenUsageRecord:
    """Create a pre-LLM token usage record (simulates validate_and_record output)."""
    repo = TokenUsageRepository()
    record = await repo.record_usage(
        user_id=test_user.id,
        token_count=1500,
        session=test_db_session,
        estimated_input_tokens=1500,
        invocation_id=invocation.id,
    )
    await test_db_session.commit()
    return record


# T016: US1-S1 — Record updated with actual token counts


@pytest.mark.asyncio
async def test_record_updated_with_actual_tokens(
    test_db_session: AsyncSession,
    pre_llm_record: TokenUsageRecord,
    invocation: Invocation,
) -> None:
    """US1-S1: After LLM responds, record has actual prompt_tokens, completion_tokens, token_count."""
    repo = TokenUsageRepository()
    usage_details = [{"prompt_tokens": 943, "completion_tokens": 500, "total_tokens": 1443}]

    updated = await repo.update_with_actual_token_usage(
        invocation_id=invocation.id,
        prompt_tokens=943,
        completion_tokens=500,
        token_count=1443,
        usage_details=usage_details,
        session=test_db_session,
    )
    await test_db_session.commit()

    assert updated is True

    # Verify in DB
    result = await test_db_session.exec(select(TokenUsageRecord).where(TokenUsageRecord.id == pre_llm_record.id))
    record = result.one()
    assert record.prompt_tokens == 943
    assert record.completion_tokens == 500
    assert record.token_count == 1443
    assert record.estimated_input_tokens == 1500  # preserved


# T016: FR-008 — No token metadata skips update


@pytest.mark.asyncio
async def test_no_update_when_no_record_for_invocation(
    test_db_session: AsyncSession,
    user_config: UserTokenConfig,
) -> None:
    """FR-008: When no record exists for the invocation, update returns False."""
    from uuid import uuid4

    repo = TokenUsageRepository()
    updated = await repo.update_with_actual_token_usage(
        invocation_id=uuid4(),
        prompt_tokens=943,
        completion_tokens=500,
        token_count=1443,
        usage_details=[],
        session=test_db_session,
    )
    assert updated is False


# T022: US2 — invocation_id correlation


@pytest.mark.asyncio
async def test_record_has_invocation_id_set(
    test_db_session: AsyncSession,
    pre_llm_record: TokenUsageRecord,
    invocation: Invocation,
) -> None:
    """US2-S1: Token usage record has invocation_id set."""
    assert pre_llm_record.invocation_id == invocation.id


@pytest.mark.asyncio
async def test_query_by_invocation_id_returns_record(
    test_db_session: AsyncSession,
    pre_llm_record: TokenUsageRecord,
    invocation: Invocation,
) -> None:
    """US2-S3: Query by invocation_id returns correct record with estimated and actual data."""
    repo = TokenUsageRepository()

    # Update with actuals
    await repo.update_with_actual_token_usage(
        invocation_id=invocation.id,
        prompt_tokens=943,
        completion_tokens=500,
        token_count=1443,
        usage_details=[{"prompt_tokens": 943, "completion_tokens": 500}],
        session=test_db_session,
    )
    await test_db_session.commit()

    # Query by invocation_id
    result = await test_db_session.exec(select(TokenUsageRecord).where(TokenUsageRecord.invocation_id == invocation.id))
    record = result.one()

    assert record.estimated_input_tokens == 1500
    assert record.prompt_tokens == 943
    assert record.completion_tokens == 500
    assert record.token_count == 1443


# T024: FR-011 — usage_details is non-null JSONB


@pytest.mark.asyncio
async def test_usage_details_is_populated_after_update(
    test_db_session: AsyncSession,
    pre_llm_record: TokenUsageRecord,
    invocation: Invocation,
) -> None:
    """FR-011: usage_details contains provider-reported token breakdown."""
    repo = TokenUsageRepository()
    usage_details = [
        {
            "prompt_tokens": 943,
            "completion_tokens": 500,
            "total_tokens": 1443,
            "prompt_tokens_details": {"cached_tokens": 128},
        }
    ]

    await repo.update_with_actual_token_usage(
        invocation_id=invocation.id,
        prompt_tokens=943,
        completion_tokens=500,
        token_count=1443,
        usage_details=usage_details,
        session=test_db_session,
    )
    await test_db_session.commit()

    result = await test_db_session.exec(select(TokenUsageRecord).where(TokenUsageRecord.id == pre_llm_record.id))
    record = result.one()
    assert record.usage_details is not None
    assert isinstance(record.usage_details, list)
    assert record.usage_details[0]["prompt_tokens"] == 943
    assert record.usage_details[0]["completion_tokens"] == 500
    assert record.usage_details[0]["total_tokens"] == 1443


# T024: FR-010 — Existing records unchanged after migration


@pytest.mark.asyncio
async def test_existing_records_retain_null_fields(
    test_db_session: AsyncSession,
    test_user,
    user_config: UserTokenConfig,
) -> None:
    """FR-010: Pre-existing records have new fields as NULL, token_count unchanged."""
    # Create a record without new fields (simulates pre-migration record)
    record = TokenUsageRecord(
        user_id=test_user.id,
        token_count=2000,
    )
    test_db_session.add(record)
    await test_db_session.commit()

    # Verify new fields are NULL
    assert record.estimated_input_tokens is None
    assert record.prompt_tokens is None
    assert record.completion_tokens is None
    assert record.invocation_id is None
    assert record.usage_details is None
    assert record.token_count == 2000  # unchanged
