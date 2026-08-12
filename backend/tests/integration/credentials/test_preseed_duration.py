"""Suite 22 — Credential Storage: Preseed Duration KPI (22.12).

Test 22.12: Application startup with 5 managed credential types preseed
    KPI: Preseed Duration < 2s added to startup
    Measurement: Startup timing
    Validation:
        - Compare startup time with and without preseed
        - Verify idempotency on repeat startup (upsert is safe to re-run)

This test exercises preseed_credential_types() directly against the
test database to isolate the preseed cost from overall application
startup. Multiple invocations verify idempotency and measure whether
repeat runs are faster (ON CONFLICT DO UPDATE short-circuit).

Run with:
    make test-integration-coverage
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.credentials.lib.preseed import GA_CREDENTIAL_TYPES, preseed_credential_types
from syntara.credentials.models.credential_type import CredentialType
from tests.integration.helpers.perf import compute_percentile

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.asyncio

TARGET_PRESEED_DURATION_MS = 2000
IDEMPOTENCY_RUNS = 10
EXPECTED_TYPE_COUNT = len(GA_CREDENTIAL_TYPES)


@pytest_asyncio.fixture
async def session_factory(
    test_db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create a session factory for the test database."""
    return async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


class TestPreseedDuration:
    """22.12 — Preseed 5 managed credential types on startup.

    Calls preseed_credential_types() directly against the test database
    to measure the wall-clock cost that would be added to application
    startup.

    Validates:
        - First preseed completes in < 2s
        - Repeat (idempotent) preseed completes in < 2s
        - Repeat runs are no slower than first run
        - All 5 credential types exist after preseed
        - Exact field/injector definitions match GA_CREDENTIAL_TYPES
    """

    async def test_preseed_duration_and_idempotency(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Preseed must complete in < 2s; repeat runs must be idempotent."""
        # --- Phase 1: First preseed (may INSERT) ---
        first_duration_ms = await _timed_preseed(session_factory)

        # Verify all 5 types exist
        types_after_first = await _fetch_managed_types(session_factory)
        assert len(types_after_first) == EXPECTED_TYPE_COUNT, (
            f"Expected {EXPECTED_TYPE_COUNT} managed types after first preseed, "
            f"got {len(types_after_first)}: {list(types_after_first.keys())}"
        )

        # --- Phase 2: Repeat preseed N times (ON CONFLICT DO UPDATE) ---
        repeat_durations: list[float] = []
        for _ in range(IDEMPOTENCY_RUNS):
            dur = await _timed_preseed(session_factory)
            repeat_durations.append(dur)

        # Verify types still correct after repeated runs
        types_after_repeat = await _fetch_managed_types(session_factory)
        assert len(types_after_repeat) == EXPECTED_TYPE_COUNT, (
            f"Expected {EXPECTED_TYPE_COUNT} managed types after repeat preseed, got {len(types_after_repeat)}"
        )

        # Verify no duplicates were created
        all_types = await _fetch_all_credential_types(session_factory)
        managed_names = [t["name"] for t in all_types if t.get("managed")]
        name_set = set(managed_names)
        duplicates = len(managed_names) - len(name_set)
        assert duplicates == 0, f"Duplicate managed credential types found: {managed_names}"

        # Verify field definitions match
        definition_mismatches = _verify_definitions(types_after_repeat)

        # --- Statistics ---
        repeat_p95 = compute_percentile(repeat_durations, 95)
        repeat_p50 = compute_percentile(repeat_durations, 50)

        diag = _build_diagnostic(
            first_duration_ms=first_duration_ms,
            repeat_durations=repeat_durations,
            repeat_p50=repeat_p50,
            repeat_p95=repeat_p95,
            types_found=len(types_after_repeat),
            duplicates=duplicates,
            definition_mismatches=definition_mismatches,
        )

        assert not definition_mismatches, f"Credential type definitions don't match GA_CREDENTIAL_TYPES{diag}"

        assert first_duration_ms < TARGET_PRESEED_DURATION_MS, (
            f"First preseed took {first_duration_ms:.1f}ms, exceeds target {TARGET_PRESEED_DURATION_MS}ms{diag}"
        )

        assert repeat_p95 < TARGET_PRESEED_DURATION_MS, (
            f"Repeat preseed p95 {repeat_p95:.1f}ms exceeds target {TARGET_PRESEED_DURATION_MS}ms{diag}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _timed_preseed(
    sf: async_sessionmaker[AsyncSession],
) -> float:
    """Run preseed_credential_types() and return elapsed time in ms."""
    async with sf() as session:
        start = time.monotonic()
        await preseed_credential_types(session)
        return (time.monotonic() - start) * 1000


async def _fetch_managed_types(
    sf: async_sessionmaker[AsyncSession],
) -> dict[str, dict[str, Any]]:
    """Fetch all managed credential types, keyed by name."""
    async with sf() as session:
        result = await session.exec(
            select(CredentialType).where(CredentialType.managed == True)  # noqa: E712
        )
        types = result.all()
        return {
            t.name: {
                "description": t.description,
                "inputs": t.inputs,
                "injectors": t.injectors,
            }
            for t in types
        }


async def _fetch_all_credential_types(
    sf: async_sessionmaker[AsyncSession],
) -> list[dict[str, Any]]:
    """Fetch all credential types (managed and custom)."""
    async with sf() as session:
        result = await session.exec(select(CredentialType))
        return [{"name": t.name, "managed": t.managed} for t in result.all()]


def _verify_definitions(
    types: dict[str, dict[str, Any]],
) -> list[str]:
    """Verify that persisted types match GA_CREDENTIAL_TYPES definitions."""
    mismatches: list[str] = []
    for ga_type in GA_CREDENTIAL_TYPES:
        name = ga_type["name"]
        if name not in types:
            mismatches.append(f"Missing type: {name!r}")
            continue
        persisted = types[name]
        if persisted["inputs"] != ga_type["inputs"]:
            mismatches.append(f"{name!r}: inputs schema mismatch")
        if persisted["injectors"] != ga_type["injectors"]:
            mismatches.append(f"{name!r}: injectors mismatch")
    return mismatches


def _build_diagnostic(
    *,
    first_duration_ms: float,
    repeat_durations: list[float],
    repeat_p50: float,
    repeat_p95: float,
    types_found: int,
    duplicates: int,
    definition_mismatches: list[str],
) -> str:
    """Build a diagnostic string for preseed duration results."""
    parts = [
        "\n--- Preseed duration results (22.12) ---",
        f"  first_preseed={first_duration_ms:.1f}ms (target < {TARGET_PRESEED_DURATION_MS}ms)",
        f"  repeat_preseed ({IDEMPOTENCY_RUNS} runs): p50={repeat_p50:.1f}ms, p95={repeat_p95:.1f}ms",
        f"  min={min(repeat_durations):.1f}ms, max={max(repeat_durations):.1f}ms",
        f"  managed_types_found={types_found}/{EXPECTED_TYPE_COUNT}",
        f"  duplicates={duplicates}",
    ]
    if definition_mismatches:
        parts.append(f"  DEFINITION MISMATCHES ({len(definition_mismatches)}):")
        for m in definition_mismatches:
            parts.append(f"    {m}")
    return "\n".join(parts) + "\n"
