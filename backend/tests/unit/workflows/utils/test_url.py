"""Tests for URL generation utilities."""

from uuid import UUID

import pytest

from syntara.core.config.base import get_settings
from syntara.workflows.utils.url import generate_activity_signal_url, get_api_base_url


def test_get_api_base_url_with_configured_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_api_base_url returns configured base URL when set."""
    # Clear settings cache
    get_settings.cache_clear()

    # Set environment variable for workflow base URL
    monkeypatch.setenv("APP_WORKFLOW_BASE_URL", "https://api.example.com")

    url = get_api_base_url()

    assert url == "https://api.example.com"

    # Clear cache for other tests
    get_settings.cache_clear()


def test_get_api_base_url_with_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_api_base_url strips trailing slash."""
    get_settings.cache_clear()

    monkeypatch.setenv("APP_WORKFLOW_BASE_URL", "https://api.example.com/")

    url = get_api_base_url()

    assert url == "https://api.example.com"
    assert not url.endswith("/")

    get_settings.cache_clear()


def test_get_api_base_url_constructs_from_host_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_api_base_url constructs URL from host and port when base URL not set."""
    get_settings.cache_clear()

    # Ensure no base URL is set
    monkeypatch.delenv("APP_WORKFLOW_BASE_URL", raising=False)

    # Set specific host and port
    monkeypatch.setenv("APP_SERVER_HOST", "localhost")
    monkeypatch.setenv("APP_SERVER_PORT", "8000")

    url = get_api_base_url()

    assert url == "http://localhost:8000/api/v1"

    get_settings.cache_clear()


def test_get_api_base_url_handles_0_0_0_0(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_api_base_url converts 0.0.0.0 to localhost."""
    get_settings.cache_clear()

    monkeypatch.delenv("APP_WORKFLOW_BASE_URL", raising=False)
    monkeypatch.setenv("APP_SERVER_HOST", "0.0.0.0")  # noqa: S104
    monkeypatch.setenv("APP_SERVER_PORT", "8000")

    url = get_api_base_url()

    assert url == "http://localhost:8000/api/v1"

    get_settings.cache_clear()


def test_generate_activity_signal_url() -> None:
    """Test generate_activity_signal_url creates correct URL."""
    execution_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    activity_id = "my_activity"

    url = generate_activity_signal_url(execution_id, activity_id)

    # URL should contain the execution ID and activity ID
    assert str(execution_id) in url
    assert activity_id in url
    assert "/api/v1/executions/" in url
    assert "/activities/" in url
    assert "/signal" in url
    assert url.endswith("/signal")


def test_generate_activity_signal_url_with_configured_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test generate_activity_signal_url uses configured base URL."""
    get_settings.cache_clear()

    monkeypatch.setenv("APP_WORKFLOW_BASE_URL", "https://api.example.com")

    execution_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    activity_id = "approval_step"

    url = generate_activity_signal_url(execution_id, activity_id)

    expected = f"https://api.example.com/executions/{execution_id}/activities/approval_step/signal"
    assert url == expected

    get_settings.cache_clear()


def test_generate_activity_signal_url_format() -> None:
    """Test generate_activity_signal_url creates well-formed URL."""
    execution_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    activity_id = "test_activity_123"

    url = generate_activity_signal_url(execution_id, activity_id)

    # Verify URL structure
    parts = url.split("/")
    assert "executions" in parts
    assert str(execution_id) in parts
    assert "activities" in parts
    assert activity_id in parts
    assert parts[-1] == "signal"
