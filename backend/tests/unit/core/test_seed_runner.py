"""Tests for the seed runner's ``--strict`` propagation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from syntara.core import seed as seed_module
from syntara.core.seed import SeederRegistration, run_seeders, strict_mode
from syntara.seed.__main__ import _build_parser

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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
            seen.append(strict_mode.get())

        registration = SeederRegistration(name="probe", func=probe, description="probe")
        with patch.object(seed_module, "_SEEDERS", [registration]):
            await run_seeders(_session_factory(), only=["probe"], strict=strict)

        assert seen == [strict]
        assert strict_mode.get() is False

    @pytest.mark.asyncio
    async def test_strict_reset_when_seeder_raises(self) -> None:
        async def boom(_session: AsyncSession) -> None:
            msg = "boom"
            raise RuntimeError(msg)

        registration = SeederRegistration(name="boom", func=boom, description="boom")
        with patch.object(seed_module, "_SEEDERS", [registration]), pytest.raises(RuntimeError):
            await run_seeders(_session_factory(), only=["boom"], strict=True)

        assert strict_mode.get() is False


class TestSeedCli:
    """The CLI exposes ``--strict`` and defaults to lenient."""

    def test_strict_flag_defaults_false(self) -> None:
        assert _build_parser().parse_args([]).strict is False

    def test_strict_flag_parsed(self) -> None:
        args = _build_parser().parse_args(["--only", "builtin_workflows", "--strict"])
        assert args.strict is True
        assert args.only == ["builtin_workflows"]
