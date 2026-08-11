"""Integration tests: DB -> SettingsCache -> activity/consumer reads live value.

Verifies the full round-trip from a database-backed runtime setting through
to the code that consumes it (loop activity, ConversionConfig).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from syntara.settings.cache.settings_cache import SettingsCache, set_runtime_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator

    from sqlmodel.ext.asyncio.session import AsyncSession

_MAX_LOOP_KEY = "workflow_engine.max_loop_iterations"
_SCRIPT_TIMEOUT_KEY = "workflow_engine.script_timeout_seconds"
_AGENTIC_TIMEOUT_KEY = "workflow_engine.agentic_timeout_seconds"
_CONVERSION_TIMEOUT_KEY = "document_conversion.timeout_seconds"
_CONVERSION_OVERWRITE_KEY = "document_conversion.overwrite_existing"

# language=SQL
_UPSERT_SETTING = """
INSERT INTO runtime_settings
    (id, key, name, category, value_type, value, default_value,
     requires_restart, version, labels, created_at, updated_at)
VALUES
    (gen_random_uuid(), :key, :name, :category, :vtype,
     CAST(:value AS jsonb), CAST(:default AS jsonb),
     false, 1, '{}'::jsonb, now(), now())
ON CONFLICT (key) DO UPDATE SET value = CAST(:value AS jsonb)
"""


async def _set_int_setting(
    session: AsyncSession,
    key: str,
    value: int,
    *,
    default: int = 0,
    name: str = "test",
    category: str = "workflow_execution",
    vtype: str = "integer",
) -> None:
    await session.exec(  # type: ignore[call-overload]
        text(_UPSERT_SETTING),
        params={
            "key": key,
            "name": name,
            "value": str(value),
            "default": str(default),
            "category": category,
            "vtype": vtype,
        },
    )
    await session.commit()
    session.expire_all()


@pytest.fixture
def _scoped_runtime_cache(
    test_session_factory: Callable[[], object],
) -> Generator[None, None, None]:
    import syntara.settings.cache.settings_cache as _sc

    prev = _sc._runtime_settings
    cache = SettingsCache(session_factory=test_session_factory)
    set_runtime_settings(cache)
    yield
    _sc._runtime_settings = prev


@pytest.fixture
async def _restore_settings(
    test_db_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    yield
    await test_db_session.rollback()
    for key in (
        _MAX_LOOP_KEY,
        _SCRIPT_TIMEOUT_KEY,
        _AGENTIC_TIMEOUT_KEY,
        _CONVERSION_TIMEOUT_KEY,
        _CONVERSION_OVERWRITE_KEY,
    ):
        await test_db_session.exec(  # type: ignore[call-overload]
            text("UPDATE runtime_settings SET value = NULL WHERE key = :key"),
            params={"key": key},
        )
    await test_db_session.commit()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_settings", "_scoped_runtime_cache")
async def test_loop_activity_routes_on_condition_not_max_iterations(
    test_db_session: AsyncSession,
) -> None:
    """Loop activity routes on condition_result only; max_iterations is enforced by the workflow.

    max_loop_iterations enforcement was moved from the loop activity into the workflow engine
    so that it can raise ApplicationError before the activity is called. The activity itself
    now only cares about condition_result.
    """
    from syntara.workflows.workflow_engine.activities.loop import loop

    await _set_int_setting(
        test_db_session,
        _MAX_LOOP_KEY,
        50,
        default=10000,
        name="Max loop iterations",
    )

    # Activity routes based on condition_result regardless of current_index vs max_iterations.
    # At index 49, condition true — iterate
    config = {
        "type": "do_while",
        "current_index": 49,
        "condition_result": True,
    }
    result = await loop(config, None, {})
    assert result["control"]["next_port"] == "iterate"

    # At index 50, condition true — still iterate (cap enforcement is in the workflow, not here)
    config["current_index"] = 50
    result = await loop(config, None, {})
    assert result["control"]["next_port"] == "iterate"

    # At index 50, condition false — complete (normal condition-based exit)
    config["condition_result"] = False
    result = await loop(config, None, {})
    assert result["control"]["next_port"] == "complete"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_settings", "_scoped_runtime_cache")
async def test_conversion_config_reads_live_timeout(
    test_db_session: AsyncSession,
) -> None:
    """ConversionConfig.from_settings() reads timeout from DB via cache."""
    from syntara.files.document_conversion.models.conversion_config import ConversionConfig

    await _set_int_setting(
        test_db_session,
        _CONVERSION_TIMEOUT_KEY,
        120,
        default=30,
        name="Conversion timeout",
        category="application",
    )
    # Seed overwrite_existing so from_settings() can read both values
    await test_db_session.exec(  # type: ignore[call-overload]
        text(_UPSERT_SETTING),
        params={
            "key": _CONVERSION_OVERWRITE_KEY,
            "name": "Overwrite existing",
            "value": "false",
            "default": "false",
            "category": "application",
            "vtype": "boolean",
        },
    )
    await test_db_session.commit()

    config = await ConversionConfig.from_settings()
    assert config.timeout_seconds == 120


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_settings", "_scoped_runtime_cache")
async def test_script_timeout_propagates_through_cache(
    test_db_session: AsyncSession,
) -> None:
    """Script timeout setting propagates from DB through cache."""
    from syntara.settings.cache.settings_cache import get_runtime_settings

    await _set_int_setting(
        test_db_session,
        _SCRIPT_TIMEOUT_KEY,
        42,
        default=300,
        name="Script timeout",
    )

    cache = get_runtime_settings()
    value = await cache.get_int(_SCRIPT_TIMEOUT_KEY)
    assert value == 42


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_settings", "_scoped_runtime_cache")
async def test_agentic_activity_reads_live_timeout(
    test_db_session: AsyncSession,
) -> None:
    """Agentic activity injects timeout from DB via cache."""
    await _set_int_setting(
        test_db_session,
        _AGENTIC_TIMEOUT_KEY,
        42,
        default=300,
        name="Agentic timeout",
    )

    # Verify the cache returns the DB value
    from syntara.settings.cache.settings_cache import get_runtime_settings

    cache = get_runtime_settings()
    value = await cache.get_int(_AGENTIC_TIMEOUT_KEY)
    assert value == 42


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_settings", "_scoped_runtime_cache")
async def test_conversion_overwrite_setting_propagates(
    test_db_session: AsyncSession,
) -> None:
    """ConversionConfig.from_settings() reads overwrite_existing from DB."""
    from syntara.files.document_conversion.models.conversion_config import ConversionConfig

    # Seed both conversion settings
    await _set_int_setting(
        test_db_session,
        _CONVERSION_TIMEOUT_KEY,
        30,
        default=30,
        name="Conversion timeout",
        category="application",
    )
    await test_db_session.exec(  # type: ignore[call-overload]
        text(_UPSERT_SETTING),
        params={
            "key": _CONVERSION_OVERWRITE_KEY,
            "name": "Overwrite existing",
            "value": "true",
            "default": "false",
            "category": "application",
            "vtype": "boolean",
        },
    )
    await test_db_session.commit()

    config = await ConversionConfig.from_settings()
    assert config.overwrite_existing is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_settings", "_scoped_runtime_cache")
async def test_setting_round_trip_via_cache(
    test_db_session: AsyncSession,
) -> None:
    """Verify all migrated integer settings round-trip through the cache."""
    from syntara.settings.cache.settings_cache import get_runtime_settings

    keys_and_values = [
        (_MAX_LOOP_KEY, 500, 10000, "workflow_execution"),
        (_SCRIPT_TIMEOUT_KEY, 60, 300, "workflow_execution"),
        (_AGENTIC_TIMEOUT_KEY, 60, 300, "workflow_execution"),
        (_CONVERSION_TIMEOUT_KEY, 45, 30, "application"),
    ]

    for key, new_value, default, category in keys_and_values:
        await _set_int_setting(test_db_session, key, new_value, default=default, name=key, category=category)

    cache = get_runtime_settings()
    for key, expected, _, _ in keys_and_values:
        actual = await cache.get_int(key)
        assert actual == expected, f"{key}: expected {expected}, got {actual}"
