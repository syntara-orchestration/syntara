"""Exact replay evidence backed by the temporary inspection store."""

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from syntara.eventstreams.core.inspection_spool import InspectionSpool
from syntara.eventstreams.core.runtime import PendingInspections


def test_matching_a_spilled_offset_keeps_its_count_and_original_timestamp() -> None:
    pending = PendingInspections(offsets=set(range(10)))
    assert pending.reserve_replay_read(10)
    snapshot = pending.copy()
    receipt = datetime(2026, 1, 1, tzinfo=UTC)

    pending.remember_match(3, receipt)
    pending.remember_match(3, receipt + timedelta(seconds=1))

    assert len(pending) == 10
    assert pending.matched_at(3) == receipt
    assert not pending.matches
    assert snapshot.matched_at(3) is None


def test_match_stays_in_memory_if_the_spill_update_fails(monkeypatch) -> None:
    pending = PendingInspections(offsets={3})
    assert pending.reserve_replay_read(1)
    receipt = datetime(2026, 1, 1, tzinfo=UTC)

    with monkeypatch.context() as patch:
        patch.setattr(InspectionSpool, "remember_match", Mock(side_effect=sqlite3.OperationalError))
        pending.remember_match(3, receipt)
        assert len(pending) == 1
        assert pending.matched_at(3) == receipt

    assert pending.matched_at(3) == receipt
    pending.remember_match(3, receipt + timedelta(seconds=1))
    assert len(pending) == 1
    assert pending.matched_at(3) == receipt


def test_failed_spill_matches_keep_exact_counts_across_copy_and_cleanup(monkeypatch) -> None:
    pending = PendingInspections(offsets={3, 5})
    assert pending.reserve_replay_read(2)
    receipt = datetime(2026, 1, 1, tzinfo=UTC)
    with monkeypatch.context() as patch:
        patch.setattr(InspectionSpool, "remember_match", Mock(side_effect=sqlite3.OperationalError))
        pending.remember_match(3, receipt)
        pending.remember_match(5, receipt)
    snapshot = pending.copy()

    pending.resolve(3)
    assert len(pending) == 1
    pending.cover_before(6)
    assert len(pending) == 0
    assert len(snapshot) == 2
    assert snapshot.reserve_replay_read(2)
    assert len(snapshot) == 2
    assert snapshot.matched_at(3) == receipt
