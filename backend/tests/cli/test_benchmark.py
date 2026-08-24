"""Tests for BenchmarkSession and module-level helpers in orchestrator_cli.benchmark."""

from __future__ import annotations

import time

import pytest
from orchestrator_cli.benchmark import BenchmarkSession, PhaseStats

# ---------------------------------------------------------------------------
# PhaseStats
# ---------------------------------------------------------------------------


def test_phase_stats_add_accumulates_totals() -> None:
    """add() updates total_s, count, min_s, and max_s correctly."""
    stats = PhaseStats()
    stats.add(0.1)
    stats.add(0.3)
    assert stats.count == 2
    assert stats.total_s == pytest.approx(0.4)
    assert stats.min_s == pytest.approx(0.1)
    assert stats.max_s == pytest.approx(0.3)


def test_phase_stats_avg_s_returns_zero_when_count_is_zero() -> None:
    assert PhaseStats().avg_s == 0.0


# ---------------------------------------------------------------------------
# BenchmarkSession — disabled
# ---------------------------------------------------------------------------


def test_disabled_session_phase_is_noop() -> None:
    """phase() must not record anything when the session is disabled."""
    session = BenchmarkSession(enabled=False)
    with session.phase("anything"):
        pass
    assert session.phases == {}


def test_disabled_session_render_lines_returns_empty_list() -> None:
    assert BenchmarkSession(enabled=False).render_lines() == []


def test_disabled_session_note_is_ignored() -> None:
    """note() must not populate metadata when disabled."""
    session = BenchmarkSession(enabled=False)
    session.note("key", "value")
    assert session.metadata == {}


# ---------------------------------------------------------------------------
# BenchmarkSession — enabled
# ---------------------------------------------------------------------------


def test_enabled_session_phase_records_timing() -> None:
    """phase() records a non-zero duration and increments count."""
    session = BenchmarkSession(enabled=True)
    with session.phase("myop"):
        time.sleep(0.01)
    assert "myop" in session.phases
    assert session.phases["myop"].count == 1
    assert session.phases["myop"].total_s > 0


def test_enabled_session_render_lines_includes_phase_stats_and_metadata() -> None:
    """render_lines() includes phase names, timing, and recorded metadata."""
    session = BenchmarkSession(enabled=True)
    session.note("cmd", "workflows list")
    session.record("myop", 0.05)
    output = "\n".join(session.render_lines())
    assert "total_s" in output
    assert "myop" in output
    assert "cmd" in output


def test_enabled_session_emit_writes_to_stderr_and_is_idempotent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """emit() writes to stderr on the first call; subsequent calls are no-ops."""
    session = BenchmarkSession(enabled=True)
    session.record("op", 0.01)

    session.emit()
    first_output = capsys.readouterr().err

    session.emit()
    second_output = capsys.readouterr().err

    assert "orchestrator benchmark" in first_output
    assert second_output == ""


def test_emit_summary_delegates_to_session(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """emit_summary() writes the session benchmark output to stderr."""
    from orchestrator_cli import benchmark as bm

    session = BenchmarkSession(enabled=True)
    session.record("startup", 0.02)
    monkeypatch.setattr(bm, "_SESSION", session)

    bm.emit_summary()

    assert "orchestrator benchmark" in capsys.readouterr().err
