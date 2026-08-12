"""Mock fixtures shared across unit and integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable


@pytest.fixture
def mock_session_factory() -> Callable[[], AsyncGenerator[Any, None]]:
    """Provide a mock database session factory for unit tests."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    async def session_gen() -> AsyncGenerator[Any, None]:
        yield mock_session

    return session_gen


@pytest.fixture
def mock_token_calculator() -> Mock:
    """Create a mock TokenCalculator for testing."""
    from syntara.agent_orchestrator.token_manager.services import TokenCalculator

    return Mock(spec=TokenCalculator)


@pytest.fixture
def mock_compressor() -> AsyncMock:
    """Create a mock CompressorService for testing."""
    return AsyncMock()
