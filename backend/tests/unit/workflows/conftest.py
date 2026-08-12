"""Shared fixtures for workflow unit tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest

from syntara.settings.cache.settings_cache import SettingsCache, set_runtime_settings
from syntara.settings.catalog import SETTINGS_CATALOG

_catalog_defaults: dict[str, int] = {
    s.key: int(s.default_value)
    for s in SETTINGS_CATALOG
    if s.key.startswith("workflow_engine.") and isinstance(s.default_value, int)
}


@pytest.fixture(autouse=True)
def _mock_runtime_settings() -> Generator[None, None, None]:
    """Provide a mock SettingsCache for all workflow activity tests.

    Activities read runtime settings from the cache. In unit tests the
    cache singleton is not initialised, so we install a mock that returns
    catalog defaults.
    """
    import syntara.settings.cache.settings_cache as _sc

    prev = _sc._runtime_settings

    mock_cache = AsyncMock(spec=SettingsCache)
    mock_cache.get_int.side_effect = lambda key, **_kw: _catalog_defaults.get(key, 0)

    set_runtime_settings(mock_cache)
    yield
    _sc._runtime_settings = prev
