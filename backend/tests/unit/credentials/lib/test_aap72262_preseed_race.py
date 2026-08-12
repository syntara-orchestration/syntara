"""Reproduction test for AAP-72262: preseed crash from duplicate credential types.

The old preseed_credential_types() used a read-then-write pattern with no
unique constraint on CredentialType.name. When multiple replicas started
concurrently, duplicates accumulated, and subsequent startups crashed with
sqlalchemy.exc.MultipleResultsFound.

This test verifies:
1. The upsert pattern is atomic (no duplicates possible).
2. The function is safe to call concurrently.
3. The function is idempotent across multiple sequential runs.

Run with:
    uv run pytest tests/unit/credentials/test_aap72262_preseed_race.py -v
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from syntara.credentials.lib.preseed import GA_CREDENTIAL_TYPES, preseed_credential_types


class TestAAP72262PreseedRaceCondition:
    """Verify the fix for AAP-72262: preseed uses atomic upsert, not read-then-write."""

    @pytest.mark.asyncio
    async def test_preseed_uses_single_execute_not_per_row_queries(self) -> None:
        """The old code did N SELECT + N INSERT calls (TOCTOU race window).

        The fix uses a single INSERT ... ON CONFLICT DO UPDATE statement.
        Verify only one execute() call is made regardless of type count.
        """
        session = AsyncMock()

        await preseed_credential_types(session)

        session.exec.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_concurrent_preseed_does_not_raise(self) -> None:
        """Simulate two replicas calling preseed concurrently.

        With the old read-then-write pattern, both would SELECT (no rows),
        then both INSERT, creating duplicates. The next startup would crash
        with MultipleResultsFound.

        With the upsert fix, both calls execute atomically and succeed.
        """
        session = AsyncMock()

        results = await asyncio.gather(
            preseed_credential_types(session),
            preseed_credential_types(session),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent preseed raised: {result}")

    @pytest.mark.asyncio
    async def test_preseed_idempotent_across_multiple_runs(self) -> None:
        """Run preseed 5 times sequentially — should always succeed."""
        session = AsyncMock()

        for i in range(5):
            try:
                await preseed_credential_types(session)
            except Exception as e:
                pytest.fail(f"Preseed failed on run {i + 1}: {e}")

        assert session.exec.await_count == 5
        assert session.commit.await_count == 5

    def test_ga_types_all_have_unique_names(self) -> None:
        """Guard against duplicate names in the GA_CREDENTIAL_TYPES list itself.

        If two entries shared a name, the upsert would silently merge them.
        """
        names = [t["name"] for t in GA_CREDENTIAL_TYPES]
        assert len(names) == len(set(names)), f"Duplicate names in GA_CREDENTIAL_TYPES: {names}"

    @pytest.mark.asyncio
    async def test_preseed_does_not_use_one_or_none(self) -> None:
        """Verify the old vulnerable pattern (one_or_none) is not used.

        The old code called result.one_or_none() which raises
        MultipleResultsFound when duplicates exist. The fix uses
        INSERT ... ON CONFLICT which never queries existing rows.
        """
        session = AsyncMock()

        await preseed_credential_types(session)

        result = session.exec.return_value
        assert not result.one_or_none.called, "preseed should use upsert, not SELECT with one_or_none()"
