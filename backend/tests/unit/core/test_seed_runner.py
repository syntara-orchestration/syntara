"""Tests for the seed runner's ``--strict`` propagation and CLI exit codes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.core import seed as seed_module
from syntara.core.seed import SeederRegistration, run_seeders
from syntara.core.seed_context import strict_mode_context_var
from syntara.seed.__main__ import _build_parser, main
from syntara.workflows.exceptions import ScheduledTriggerSyncError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Coroutine

    from sqlmodel.ext.asyncio.session import AsyncSession


def _session_factory() -> object:
    @asynccontextmanager
    async def _factory() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    return _factory


class TestRunSeedersStrict:
    """``run_seeders(strict=...)`` exposes the flag to seeders for the pass only."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("strict", [True, False])
    async def test_strict_visible_to_seeder_and_reset_after(self, *, strict: bool) -> None:
        seen: list[bool] = []

        async def probe(_session: AsyncSession) -> None:
            seen.append(strict_mode_context_var.get())

        registration = SeederRegistration(name="probe", func=probe, description="probe")
        with patch.object(seed_module, "_SEEDERS", [registration]):
            await run_seeders(_session_factory(), only=["probe"], strict=strict)

        assert seen == [strict]
        assert strict_mode_context_var.get() is False

    @pytest.mark.asyncio
    async def test_strict_reset_when_seeder_raises(self) -> None:
        async def boom(_session: AsyncSession) -> None:
            msg = "boom"
            raise RuntimeError(msg)

        registration = SeederRegistration(name="boom", func=boom, description="boom")
        with patch.object(seed_module, "_SEEDERS", [registration]), pytest.raises(RuntimeError):
            await run_seeders(_session_factory(), only=["boom"], strict=True)

        assert strict_mode_context_var.get() is False


class TestSeedCli:
    """The CLI exposes ``--strict`` and defaults to lenient."""

    def test_strict_flag_defaults_false(self) -> None:
        assert _build_parser().parse_args([]).strict is False

    def test_strict_flag_parsed(self) -> None:
        args = _build_parser().parse_args(["--only", "builtin_workflows", "--strict"])
        assert args.strict is True
        assert args.only == ["builtin_workflows"]


def _strict_contract_probe(seen: list[bool]) -> Callable[[AsyncSession], Coroutine[Any, Any, None]]:
    """Seeder mirroring ``_sync_builtin_schedules``' strict contract.

    A Temporal sync failure raises only in strict mode; otherwise it degrades.
    """

    async def probe(_session: AsyncSession) -> None:
        seen.append(strict_mode_context_var.get())
        if strict_mode_context_var.get():
            workflow_id = "probe-workflow"
            raise ScheduledTriggerSyncError(workflow_id, 1)

    return probe


class TestSeedCliExitCode:
    """``main()`` joins the --strict flag, ContextVar propagation, and exit code.

    The parser (flag parsing) and the ContextVar (strict visibility) are each
    tested in isolation above; these drive the real CLI entry point so the
    documented contract — a failed Schedule sync exits non-zero only under
    ``--strict`` — holds end to end.
    """

    @staticmethod
    def _run_main(argv: list[str], seen: list[bool]) -> None:
        registration = SeederRegistration(
            name="probe",
            func=_strict_contract_probe(seen),
            description="probe",
        )
        with (
            patch.object(seed_module, "_SEEDERS", [registration]),
            patch("sys.argv", ["syntara.seed", "--only", "probe", *argv]),
            patch("syntara.seed.__main__.start_audit_subsystems"),
            patch("syntara.seed.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch("syntara.core.database.session.AsyncSessionLocal", _session_factory()),
        ):
            main()

    def test_strict_sync_failure_exits_non_zero(self) -> None:
        """Under ``--strict`` the seeder's sync failure exits with code 1."""
        seen: list[bool] = []
        with pytest.raises(SystemExit) as exc_info:
            self._run_main(["--strict"], seen)

        assert exc_info.value.code == 1
        assert seen == [True]

    def test_lenient_sync_failure_exits_zero(self) -> None:
        """Without ``--strict`` the same failure degrades and the CLI exits 0."""
        seen: list[bool] = []
        self._run_main([], seen)

        assert seen == [False]
