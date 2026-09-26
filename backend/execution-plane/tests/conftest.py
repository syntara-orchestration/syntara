"""Shared fixtures for execution-plane unit tests."""

from collections.abc import Generator

import pytest
from execution_plane.config import get_ep_settings, get_script_executor_settings


@pytest.fixture(autouse=True)
def ep_settings_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Set the minimum required env vars for EPSettings and clear lru_caches."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost/test")
    get_ep_settings.cache_clear()
    get_script_executor_settings.cache_clear()
    yield
    get_ep_settings.cache_clear()
    get_script_executor_settings.cache_clear()
