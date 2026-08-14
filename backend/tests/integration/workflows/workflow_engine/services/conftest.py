"""Shared fixtures for integration/services tests."""

from collections.abc import Generator

import pytest

from tests.fixtures.settings import FakeSettingsCache, enable_script_nodes


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

    with enable_script_nodes():
        try:
            yield
        finally:
            _settings_mod._runtime_settings = original
