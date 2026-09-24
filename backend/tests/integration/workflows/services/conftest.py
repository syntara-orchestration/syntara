"""Shared fixtures for workflow service integration tests."""

from collections.abc import Generator

import pytest

from tests.fixtures.settings import FakeSettingsCache


@pytest.fixture(autouse=True)
def _ensure_runtime_settings() -> Generator[None, None, None]:
    """Install a fake SettingsCache when no process-wide one is registered.

    The workflow service reads runtime settings (``workflow_engine.continue_on_failure``,
    ``workflows.disabled_node_kinds``) on every save.  Tests that need specific
    values install their own cache; everything else gets an empty fake so the
    save paths do not fail with "SettingsCache has not been initialised".
    """
    import syntara.settings.cache.settings_cache as _settings_mod

    original = _settings_mod._runtime_settings
    if original is None:
        _settings_mod._runtime_settings = FakeSettingsCache()  # type: ignore[assignment]
    try:
        yield
    finally:
        _settings_mod._runtime_settings = original
