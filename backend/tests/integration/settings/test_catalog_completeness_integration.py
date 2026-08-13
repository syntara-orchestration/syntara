"""Integration tests for the startup catalog completeness check."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import sqlalchemy

from syntara.api.main import _check_settings_catalog
from syntara.settings.seeder import seed_settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_raises_when_not_seeded(
    test_db_engine: AsyncEngine,
    test_session_factory: Callable[[], object],
) -> None:
    """Startup check raises RuntimeError when settings are not seeded."""
    async with test_db_engine.begin() as conn:
        await conn.execute(sqlalchemy.text("DELETE FROM runtime_settings"))
    with pytest.raises(RuntimeError, match="runtime settings have not been seeded"):
        await _check_settings_catalog(session_factory=test_session_factory)


@pytest.mark.asyncio
async def test_passes_after_seeding(
    test_session_factory: Callable[[], object],
) -> None:
    """Startup check passes silently after running the seeder."""
    await seed_settings(test_session_factory)
    await _check_settings_catalog(session_factory=test_session_factory)
