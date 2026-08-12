"""Unit tests for SettingsCache typed getter methods.

Tests cover:
- get_int / get_float / get_str / get_bool happy paths
- Type mismatch raises SettingTypeError
- get_int rejects bool values
- None with default returns default
- None without default raises SettingTypeError
- get_float coerces int to float
"""

from __future__ import annotations

import pytest

from syntara.settings.exceptions import SettingTypeError

# FakeSettingsCache mirrors SettingsCache's typed getter interface.
from tests.fixtures.settings import FakeSettingsCache

# ---------------------------------------------------------------------------
# get_int
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_int_returns_int() -> None:
    """get_int returns an int value from the store."""
    cache = FakeSettingsCache()
    result = await cache.get_int("context_manager.max_total_tokens")
    assert result == 4000
    assert isinstance(result, int)


@pytest.mark.asyncio
async def test_get_int_rejects_bool() -> None:
    """get_int raises SettingTypeError for bool values."""
    cache = FakeSettingsCache({"context_manager.max_total_tokens": True})
    with pytest.raises(SettingTypeError, match="expected type int, got bool"):
        await cache.get_int("context_manager.max_total_tokens")


@pytest.mark.asyncio
async def test_get_int_rejects_string() -> None:
    """get_int raises SettingTypeError for string values."""
    cache = FakeSettingsCache({"context_manager.max_total_tokens": "not_a_number"})
    with pytest.raises(SettingTypeError, match="expected type int, got str"):
        await cache.get_int("context_manager.max_total_tokens")


@pytest.mark.asyncio
async def test_get_int_none_with_default() -> None:
    """get_int returns default when value is None."""
    cache = FakeSettingsCache({"context_manager.max_total_tokens": None})
    result = await cache.get_int("context_manager.max_total_tokens", default=42)
    assert result == 42


@pytest.mark.asyncio
async def test_get_int_none_without_default() -> None:
    """get_int raises SettingTypeError when value is None and no default."""
    cache = FakeSettingsCache({"context_manager.max_total_tokens": None})
    with pytest.raises(SettingTypeError, match="expected type int, got None"):
        await cache.get_int("context_manager.max_total_tokens")


# ---------------------------------------------------------------------------
# get_float
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_float_returns_float() -> None:
    """get_float returns a float value from the store."""
    cache = FakeSettingsCache()
    result = await cache.get_float("context_manager.compression_temperature")
    assert result == 0.3
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_get_float_coerces_int_to_float() -> None:
    """get_float accepts int and returns it as a float."""
    cache = FakeSettingsCache({"context_manager.compression_temperature": 1})
    result = await cache.get_float("context_manager.compression_temperature")
    assert result == 1.0
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_get_float_rejects_string() -> None:
    """get_float raises SettingTypeError for string values."""
    cache = FakeSettingsCache({"context_manager.compression_temperature": "bad"})
    with pytest.raises(SettingTypeError, match="expected type float, got str"):
        await cache.get_float("context_manager.compression_temperature")


@pytest.mark.asyncio
async def test_get_float_rejects_bool() -> None:
    """get_float raises SettingTypeError for bool values."""
    cache = FakeSettingsCache({"context_manager.compression_temperature": True})
    with pytest.raises(SettingTypeError, match="expected type float, got bool"):
        await cache.get_float("context_manager.compression_temperature")


@pytest.mark.asyncio
async def test_get_float_none_with_default() -> None:
    """get_float returns default when value is None."""
    cache = FakeSettingsCache({"context_manager.compression_temperature": None})
    result = await cache.get_float("context_manager.compression_temperature", default=0.5)
    assert result == 0.5


# ---------------------------------------------------------------------------
# get_str
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_str_returns_str() -> None:
    """get_str returns a string value from the store."""
    cache = FakeSettingsCache()
    result = await cache.get_str("context_manager.compression_mode")
    assert result == "extractive"
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_get_str_rejects_int() -> None:
    """get_str raises SettingTypeError for int values."""
    cache = FakeSettingsCache({"context_manager.compression_mode": 42})
    with pytest.raises(SettingTypeError, match="expected type str, got int"):
        await cache.get_str("context_manager.compression_mode")


@pytest.mark.asyncio
async def test_get_str_none_with_default() -> None:
    """get_str returns default when value is None."""
    cache = FakeSettingsCache({"context_manager.compression_mode": None})
    result = await cache.get_str("context_manager.compression_mode", default="fallback")
    assert result == "fallback"


# ---------------------------------------------------------------------------
# Read-time validation against catalog constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_str_rejects_invalid_allowed_value() -> None:
    """get_str returns catalog default when DB value violates allowed_values."""
    cache = FakeSettingsCache({"context_manager.compression_mode": "invalid_mode"})
    result = await cache.get_str("context_manager.compression_mode")
    assert result == "extractive"  # catalog default


@pytest.mark.asyncio
async def test_get_int_rejects_below_min() -> None:
    """get_int returns catalog default when DB value is below min constraint."""
    cache = FakeSettingsCache({"context_manager.max_total_tokens": -1})
    result = await cache.get_int("context_manager.max_total_tokens")
    assert result == 4000  # catalog default


@pytest.mark.asyncio
async def test_get_float_rejects_above_max() -> None:
    """get_float returns catalog default when DB value exceeds max constraint."""
    cache = FakeSettingsCache({"context_manager.required_grounding_score": 2.5})
    result = await cache.get_float("context_manager.required_grounding_score")
    assert result == 0.7  # catalog default


@pytest.mark.asyncio
async def test_get_str_passes_valid_allowed_value() -> None:
    """get_str returns the DB value when it satisfies allowed_values."""
    cache = FakeSettingsCache({"context_manager.compression_mode": "abstractive"})
    result = await cache.get_str("context_manager.compression_mode")
    assert result == "abstractive"


# ---------------------------------------------------------------------------
# get_bool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_bool_returns_bool() -> None:
    """get_bool returns a bool value from the store."""
    cache = FakeSettingsCache()
    result = await cache.get_bool("context_manager.enable_hybrid_search")
    assert result is True
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_get_bool_rejects_int() -> None:
    """get_bool raises SettingTypeError for int values."""
    cache = FakeSettingsCache({"context_manager.enable_hybrid_search": 1})
    with pytest.raises(SettingTypeError, match="expected type bool, got int"):
        await cache.get_bool("context_manager.enable_hybrid_search")


@pytest.mark.asyncio
async def test_get_bool_none_with_default() -> None:
    """get_bool returns default when value is None."""
    cache = FakeSettingsCache({"context_manager.enable_hybrid_search": None})
    result = await cache.get_bool("context_manager.enable_hybrid_search", default=False)
    assert result is False
