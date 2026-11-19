"""Shared fixtures for integration/services tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.fixtures.settings import FakeSettingsCache

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def _ensure_runtime_settings() -> Generator[None, None, None]:
    """Ensure the SettingsCache singleton is initialised for temporal tests.

    Script activities call ``get_runtime_settings()``
    which raises ``RuntimeError`` if the singleton has not been set.
    """
    import syntara.settings.cache.settings_cache as _settings_mod

    original = _settings_mod._runtime_settings
    _settings_mod._runtime_settings = FakeSettingsCache()  # type: ignore[assignment]

    try:
        yield
    finally:
        _settings_mod._runtime_settings = original
