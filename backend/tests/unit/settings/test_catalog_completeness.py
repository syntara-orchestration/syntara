"""Tests for the startup catalog completeness check."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.settings.store import check_catalog_completeness


@pytest.mark.asyncio
async def test_returns_missing_keys() -> None:
    """Returns keys present in the catalog but absent from the database."""
    catalog_keys = {d.key for d in SETTINGS_CATALOG}
    db_keys = {SETTINGS_CATALOG[0].key}

    mock_result = MagicMock()
    mock_result.all.return_value = list(db_keys)
    mock_session = AsyncMock()
    mock_session.exec.return_value = mock_result

    missing = await check_catalog_completeness(mock_session)
    assert missing == catalog_keys - db_keys


@pytest.mark.asyncio
async def test_returns_empty_when_complete() -> None:
    """Returns empty set when all catalog keys exist in the database."""
    all_keys = [d.key for d in SETTINGS_CATALOG]

    mock_result = MagicMock()
    mock_result.all.return_value = all_keys
    mock_session = AsyncMock()
    mock_session.exec.return_value = mock_result

    missing = await check_catalog_completeness(mock_session)
    assert missing == set()


@pytest.mark.asyncio
async def test_ignores_extra_db_keys() -> None:
    """Extra keys in the database not in the catalog are not reported."""
    all_keys = [d.key for d in SETTINGS_CATALOG]
    all_keys.append("stale.removed_setting")

    mock_result = MagicMock()
    mock_result.all.return_value = all_keys
    mock_session = AsyncMock()
    mock_session.exec.return_value = mock_result

    missing = await check_catalog_completeness(mock_session)
    assert missing == set()


@pytest.mark.asyncio
async def test_all_missing_when_db_empty() -> None:
    """All catalog keys are missing when the table is empty."""
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session = AsyncMock()
    mock_session.exec.return_value = mock_result

    missing = await check_catalog_completeness(mock_session)
    assert missing == {d.key for d in SETTINGS_CATALOG}
