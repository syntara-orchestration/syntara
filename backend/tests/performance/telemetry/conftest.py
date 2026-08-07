"""Shared fixtures for telemetry performance tests."""

from collections.abc import Generator

import pytest

from nexus.core.config.base import get_settings


@pytest.fixture(autouse=True)
def _enable_script_nodes() -> Generator[None, None, None]:
    """Enable script nodes for telemetry overhead tests that call execute_script_activity directly."""
    settings = get_settings()
    original = settings.script_nodes_enabled
    object.__setattr__(settings, "script_nodes_enabled", True)
    try:
        yield
    finally:
        object.__setattr__(settings, "script_nodes_enabled", original)
