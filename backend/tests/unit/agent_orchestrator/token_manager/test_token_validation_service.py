"""Unit tests for TokenValidationService."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.token_manager.exceptions import (
    TokenLimitExceededError,
    UserTokenConfigNotFoundError,
)
from syntara.agent_orchestrator.token_manager.models import UserTokenConfig
from syntara.agent_orchestrator.token_manager.repository import TokenUsageRepository
from syntara.agent_orchestrator.token_manager.services import (
    TokenCalculator,
    TokenValidationService,
)


@pytest.fixture
def mock_calculator() -> MagicMock:
    """Create a mock TokenCalculator."""
    calculator = MagicMock(spec=TokenCalculator)
    calculator.count_tokens.return_value = 1000
    return calculator


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create a mock TokenUsageRepository."""
    return AsyncMock(spec=TokenUsageRepository)


@pytest.fixture
def service(mock_calculator: MagicMock, mock_repository: AsyncMock) -> TokenValidationService:
    """Create a TokenValidationService with mocked dependencies."""
    return TokenValidationService(calculator=mock_calculator, repository=mock_repository)


@pytest.fixture
def user_config() -> UserTokenConfig:
    """Create a test user configuration."""
    return UserTokenConfig(
        user_id=uuid4(),
        token_limit=10000,
        window_duration_seconds=3600,
    )


@pytest.mark.asyncio
async def test_validate_and_record_within_limit(
    service: TokenValidationService,
    mock_calculator: MagicMock,
    mock_repository: AsyncMock,
    user_config: UserTokenConfig,
) -> None:
    """Test that requests within limit are accepted and recorded."""
    # Arrange
    mock_session = AsyncMock()

    mock_repository.get_user_config.return_value = user_config  # Preliminary read for model_name
    mock_repository.get_user_config_with_lock.return_value = user_config
    mock_repository.calculate_current_usage.return_value = 8000  # Current usage
    mock_calculator.count_tokens.return_value = 1500  # Request tokens

    # Act
    tokens = await service.validate_and_record(
        user_id=user_config.user_id,
        request_text="test request",
        session=mock_session,
    )

    # Assert
    assert tokens == 1500
    mock_calculator.count_tokens.assert_called_once_with("test request", model_name="gpt-4")
    mock_repository.get_user_config_with_lock.assert_called_once_with(user_config.user_id, mock_session)
    mock_repository.calculate_current_usage.assert_called_once_with(
        user_id=user_config.user_id,
        window_duration_seconds=3600,
        session=mock_session,
    )
    mock_repository.record_usage.assert_called_once_with(
        user_id=user_config.user_id,
        token_count=1500,
        session=mock_session,
        estimated_input_tokens=1500,
        invocation_id=None,
    )


@pytest.mark.asyncio
async def test_validate_and_record_exceeds_limit(
    service: TokenValidationService,
    mock_calculator: MagicMock,
    mock_repository: AsyncMock,
    user_config: UserTokenConfig,
) -> None:
    """Test that TokenLimitExceededError is raised when limit exceeded."""
    # Arrange
    mock_session = AsyncMock()

    mock_repository.get_user_config.return_value = user_config  # Preliminary read for model_name
    mock_repository.get_user_config_with_lock.return_value = user_config
    mock_repository.calculate_current_usage.return_value = 9500  # Current usage
    mock_calculator.count_tokens.return_value = 1000  # Request tokens (would exceed 10000)

    # Act & Assert
    with pytest.raises(TokenLimitExceededError) as exc_info:
        await service.validate_and_record(
            user_id=user_config.user_id,
            request_text="test request",
            session=mock_session,
        )

    # Verify exception details
    error = exc_info.value
    assert error.user_id == user_config.user_id
    assert error.current_usage == 9500
    assert error.token_limit == 10000
    assert error.request_tokens == 1000
    assert str(user_config.user_id) not in str(error)
    assert "Token limit exceeded for user" not in str(error)
    assert "model token limit" in str(error)

    # Verify usage was NOT recorded
    mock_repository.record_usage.assert_not_called()


@pytest.mark.asyncio
async def test_validate_and_record_single_large_request(
    service: TokenValidationService,
    mock_calculator: MagicMock,
    mock_repository: AsyncMock,
    user_config: UserTokenConfig,
) -> None:
    """Test that single request exceeding limit is blocked."""
    # Arrange
    mock_session = AsyncMock()

    mock_repository.get_user_config.return_value = user_config  # Preliminary read for model_name
    mock_repository.get_user_config_with_lock.return_value = user_config
    mock_repository.calculate_current_usage.return_value = 0  # No current usage
    mock_calculator.count_tokens.return_value = 12000  # Request alone exceeds limit

    # Act & Assert
    with pytest.raises(TokenLimitExceededError) as exc_info:
        await service.validate_and_record(
            user_id=user_config.user_id,
            request_text="large request",
            session=mock_session,
        )

    # Verify exception details
    error = exc_info.value
    assert error.current_usage == 0
    assert error.request_tokens == 12000
    assert error.token_limit == 10000

    # Verify usage was NOT recorded
    mock_repository.record_usage.assert_not_called()


@pytest.mark.asyncio
async def test_validate_and_record_no_config(
    service: TokenValidationService,
    mock_calculator: MagicMock,
    mock_repository: AsyncMock,
) -> None:
    """Test that UserTokenConfigNotFoundError is raised when config missing."""
    # Arrange
    user_id = uuid4()
    mock_session = AsyncMock()

    mock_repository.get_user_config.side_effect = UserTokenConfigNotFoundError(user_id)  # Preliminary read fails
    mock_repository.get_user_config_with_lock.side_effect = UserTokenConfigNotFoundError(user_id)
    mock_calculator.count_tokens.return_value = 1000

    # Act & Assert
    with pytest.raises(UserTokenConfigNotFoundError) as exc_info:
        await service.validate_and_record(
            user_id=user_id,
            request_text="test",
            session=mock_session,
        )

    assert exc_info.value.user_id == user_id

    # Verify usage was NOT recorded
    mock_repository.record_usage.assert_not_called()


@pytest.mark.asyncio
async def test_get_current_usage(
    service: TokenValidationService,
    mock_repository: AsyncMock,
    user_config: UserTokenConfig,
) -> None:
    """Test getting current usage statistics."""
    # Arrange
    mock_session = AsyncMock()
    mock_repository.get_user_config.return_value = user_config
    mock_repository.calculate_current_usage.return_value = 6500

    # Act
    result = await service.get_current_usage(
        user_id=user_config.user_id,
        session=mock_session,
    )

    # Assert
    assert result["current_usage"] == 6500
    assert result["token_limit"] == 10000
    assert result["remaining"] == 3500
    assert result["window_duration_seconds"] == 3600

    mock_repository.get_user_config.assert_called_once_with(user_config.user_id, mock_session)
    mock_repository.calculate_current_usage.assert_called_once_with(
        user_id=user_config.user_id,
        window_duration_seconds=3600,
        session=mock_session,
    )


@pytest.mark.asyncio
async def test_get_current_usage_no_usage(
    service: TokenValidationService,
    mock_repository: AsyncMock,
    user_config: UserTokenConfig,
) -> None:
    """Test getting current usage when no usage exists."""
    # Arrange
    mock_session = AsyncMock()
    mock_repository.get_user_config.return_value = user_config
    mock_repository.calculate_current_usage.return_value = 0

    # Act
    result = await service.get_current_usage(
        user_id=user_config.user_id,
        session=mock_session,
    )

    # Assert
    assert result["current_usage"] == 0
    assert result["token_limit"] == 10000
    assert result["remaining"] == 10000


# T007: validate_and_record with invocation_id


@pytest.mark.asyncio
async def test_validate_and_record_passes_invocation_id(
    service: TokenValidationService,
    mock_calculator: MagicMock,
    mock_repository: AsyncMock,
    user_config: UserTokenConfig,
) -> None:
    """Test that validate_and_record passes invocation_id to record_usage."""
    mock_session = AsyncMock()
    mock_nested = AsyncMock()
    mock_nested.__aenter__ = AsyncMock(return_value=None)
    mock_nested.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin_nested = MagicMock(return_value=mock_nested)

    mock_repository.get_user_config.return_value = user_config
    mock_repository.get_user_config_with_lock.return_value = user_config
    mock_repository.calculate_current_usage.return_value = 0
    mock_calculator.count_tokens.return_value = 1500

    invocation_id = uuid4()

    tokens = await service.validate_and_record(
        user_id=user_config.user_id,
        request_text="test request",
        session=mock_session,
        invocation_id=invocation_id,
    )

    assert tokens == 1500
    mock_repository.record_usage.assert_called_once_with(
        user_id=user_config.user_id,
        token_count=1500,
        session=mock_session,
        estimated_input_tokens=1500,
        invocation_id=invocation_id,
    )


@pytest.mark.asyncio
async def test_validate_and_record_sets_estimated_input_tokens_equal_to_token_count(
    service: TokenValidationService,
    mock_calculator: MagicMock,
    mock_repository: AsyncMock,
    user_config: UserTokenConfig,
) -> None:
    """Test that estimated_input_tokens is set equal to token_count."""
    mock_session = AsyncMock()
    mock_nested = AsyncMock()
    mock_nested.__aenter__ = AsyncMock(return_value=None)
    mock_nested.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin_nested = MagicMock(return_value=mock_nested)

    mock_repository.get_user_config.return_value = user_config
    mock_repository.get_user_config_with_lock.return_value = user_config
    mock_repository.calculate_current_usage.return_value = 0
    mock_calculator.count_tokens.return_value = 2000

    tokens = await service.validate_and_record(
        user_id=user_config.user_id,
        request_text="test request",
        session=mock_session,
    )

    assert tokens == 2000
    # estimated_input_tokens should equal token_count
    call_kwargs = mock_repository.record_usage.call_args[1]
    assert call_kwargs["estimated_input_tokens"] == 2000
