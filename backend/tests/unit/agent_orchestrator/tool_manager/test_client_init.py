"""Tests for ToolManagerClient initialization and configuration."""

import httpx
import pytest

from syntara.agent_orchestrator.tool_manager.tool_manager_client import ToolManagerClient
from syntara.core.exceptions import SafeValueError


class TestToolManagerClientInit:
    """Test client initialization scenarios."""

    def test_client_init_default_config(self) -> None:
        """Test client initialization with default configuration."""
        client = ToolManagerClient(base_url="http://localhost:8000")

        assert client.base_url == "http://localhost:8000"
        assert client.timeout == pytest.approx(30.0)  # default timeout
        assert isinstance(client.session, httpx.AsyncClient)

    def test_client_init_custom_timeout(self) -> None:
        """Test client initialization with custom timeout."""
        client = ToolManagerClient(base_url="http://localhost:8000", timeout=60.0)

        assert client.base_url == "http://localhost:8000"
        assert client.timeout == pytest.approx(60.0)

    def test_client_init_invalid_url(self) -> None:
        """Test client initialization with invalid base URL."""
        with pytest.raises(SafeValueError, match="Invalid base URL"):
            ToolManagerClient(base_url="invalid-url")

    def test_client_init_negative_timeout(self) -> None:
        """Test client initialization with negative timeout."""
        with pytest.raises(SafeValueError, match="Timeout must be positive"):
            ToolManagerClient(base_url="http://localhost:8000", timeout=-1.0)

    def test_client_init_invalid_limit(self) -> None:
        """Test client initialization with invalid limit values."""
        # Test negative limit
        with pytest.raises(SafeValueError, match="Limit must be positive"):
            ToolManagerClient(base_url="http://localhost:8000", limit=-1)

        # Test zero limit
        with pytest.raises(SafeValueError, match="Limit must be positive"):
            ToolManagerClient(base_url="http://localhost:8000", limit=0)

    def test_client_init_invalid_max_connections(self) -> None:
        """Test client initialization with invalid max_connections values."""
        # Test negative max_connections
        with pytest.raises(SafeValueError, match="max_connections must be positive"):
            ToolManagerClient(base_url="http://localhost:8000", max_connections=-1)

        # Test zero max_connections
        with pytest.raises(SafeValueError, match="max_connections must be positive"):
            ToolManagerClient(base_url="http://localhost:8000", max_connections=0)

    def test_client_init_valid_max_connections(self) -> None:
        """Test client initialization with valid max_connections values."""
        # Test with custom max_connections
        client = ToolManagerClient(base_url="http://localhost:8000", max_connections=20)
        assert client.max_connections == 20

        # Test with default max_connections
        client_default = ToolManagerClient(base_url="http://localhost:8000")
        assert client_default.max_connections == 10

    def test_client_init_invalid_max_keepalive_connections(self) -> None:
        """Test client initialization with invalid max_keepalive_connections values."""
        # Test negative max_keepalive_connections
        with pytest.raises(SafeValueError, match="max_keepalive_connections must be non-negative"):
            ToolManagerClient(base_url="http://localhost:8000", max_keepalive_connections=-1)

        # Test max_keepalive_connections exceeding max_connections
        with pytest.raises(SafeValueError, match="max_keepalive_connections cannot exceed max_connections"):
            ToolManagerClient(base_url="http://localhost:8000", max_connections=5, max_keepalive_connections=10)

    def test_client_init_valid_max_keepalive_connections(self) -> None:
        """Test client initialization with valid max_keepalive_connections values."""
        # Test with custom max_keepalive_connections
        client = ToolManagerClient(base_url="http://localhost:8000", max_keepalive_connections=3)
        assert client.max_keepalive_connections == 3

        # Test with default max_keepalive_connections
        client_default = ToolManagerClient(base_url="http://localhost:8000")
        assert client_default.max_keepalive_connections == 5

        # Test with zero max_keepalive_connections (valid edge case)
        client_zero = ToolManagerClient(base_url="http://localhost:8000", max_keepalive_connections=0)
        assert client_zero.max_keepalive_connections == 0

        # Test with max_keepalive_connections equal to max_connections (valid edge case)
        client_equal = ToolManagerClient(
            base_url="http://localhost:8000", max_connections=10, max_keepalive_connections=10
        )
        assert client_equal.max_keepalive_connections == 10
        assert client_equal.max_connections == 10

    def test_client_init_valid_limit(self) -> None:
        """Test client initialization with valid limit values."""
        # Test with positive limit
        client = ToolManagerClient(base_url="http://localhost:8000", limit=50)
        assert client.limit == 50

        # Test with None limit (default)
        client_default = ToolManagerClient(base_url="http://localhost:8000")
        assert client_default.limit is None

        # Test with explicit None limit
        client_none = ToolManagerClient(base_url="http://localhost:8000", limit=None)
        assert client_none.limit is None

    def test_client_session_configured_properly(self) -> None:
        """Test that HTTP session is configured with proper settings."""
        client = ToolManagerClient(base_url="http://localhost:8000", timeout=45.0)

        # Verify session is configured with timeout
        # httpx.Timeout(45.0) sets all timeout types to 45.0
        assert client.session.timeout.connect == pytest.approx(45.0)
        assert client.session.timeout.read == pytest.approx(45.0)
        assert client.session.timeout.write == pytest.approx(45.0)
        assert client.session.timeout.pool == pytest.approx(45.0)
        assert client.session.base_url == "http://localhost:8000"

    async def test_client_close(self) -> None:
        """Test client cleanup when closed."""
        client = ToolManagerClient(base_url="http://localhost:8000")

        # Verify session is created
        assert client.session is not None
        assert not client.session.is_closed

        # Close client
        await client.close()

        # Verify session is closed
        assert client.session.is_closed

    async def test_client_context_manager_usage(self) -> None:
        """Test client works properly as async context manager."""
        async with ToolManagerClient(base_url="http://localhost:8000") as client:
            # Verify client is usable within context
            assert client.session is not None
            assert not client.session.is_closed

        # Verify cleanup happened after context exit
        assert client.session.is_closed
