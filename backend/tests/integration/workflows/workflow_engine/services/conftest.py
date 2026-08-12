"""Shared fixtures for integration/services tests."""

from collections.abc import Generator

import pytest

from syntara.core.config.base import get_settings
from tests.fixtures.settings import FakeSettingsCache


@pytest.fixture(autouse=True)
def _ensure_runtime_settings() -> Generator[None, None, None]:
    """Ensure the SettingsCache singleton is initialised for temporal tests.

    Activities like ``execute_script_activity`` call ``get_runtime_settings()``
    which raises ``RuntimeError`` if the singleton has not been set.
    Also enables script nodes since the gate defaults to False.
    """
    import syntara.settings.cache.settings_cache as _settings_mod

    original = _settings_mod._runtime_settings
    _settings_mod._runtime_settings = FakeSettingsCache()  # type: ignore[assignment]

    settings = get_settings()
    original_script_nodes = settings.script_nodes_enabled
    object.__setattr__(settings, "script_nodes_enabled", True)

    try:
        yield
    finally:
        object.__setattr__(settings, "script_nodes_enabled", original_script_nodes)
        _settings_mod._runtime_settings = original
