"""Deterministic pending-event application order in the activity synchronizer.

``pending_sync_event_ids`` is a ``set``; its iteration order is not Temporal event
order. For a ``for_each`` sub-workflow node every iteration maps to the same
aggregate ActivityExecution row, so the synchronizer must apply pending updates in
event-id order to make the winning ``input_data``/``output_data`` (and the emitted
WebSocket state) deterministic. These tests drive ``ActivityExecutionSynchronizer.sync``
with a fake host and assert ascending event-id processing regardless of set
insertion order. Row-level I/O determinism and WebSocket state are covered by the
DB-backed integration suite.
"""

from __future__ import annotations

from typing import Self
from unittest.mock import Mock
from uuid import uuid4

from syntara.workflows.workflow_engine.services.activity_execution_synchronizer import (
    ActivityExecutionSynchronizer,
)
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata

_Update = dict[str, int]


class _Result:
    def all(self) -> list[object]:
        return []

    def one_or_none(self) -> object | None:
        return None


class _FakeSession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def exec(self, _stmt: object) -> _Result:
        return _Result()

    async def commit(self) -> None:
        """No-op commit."""

    async def rollback(self) -> None:
        """No-op rollback."""


class _FakeHost:
    """Minimal synchronizer host that records the order updates are applied in."""

    def __init__(self) -> None:
        self.processed: list[int] = []
        self._session = _FakeSession()

    def session_factory(self) -> _FakeSession:
        return self._session

    async def _process_single_activity_sync(
        self,
        _metadata: ExecutionMonitorMetadata,
        _handle: object,
        activity_data: _Update,
        _existing: object,
        _session: _FakeSession,
    ) -> None:
        self.processed.append(activity_data["_eid"])

    def _collect_terminal_activities(
        self, _metadata: ExecutionMonitorMetadata
    ) -> tuple[list[object], list[object], dict[int, object]]:
        return ([], [], {})

    def _update_execution_flags(
        self, _execution: object, _updated: object, _existing: object
    ) -> tuple[object | None, bool]:
        return (None, False)

    async def _publish_patches_and_emit_telemetry(self, *_a: object, **_k: object) -> None:
        """No-op publish."""


def _metadata(updates: dict[int, _Update], pending: set[int]) -> ExecutionMonitorMetadata:
    return ExecutionMonitorMetadata(
        execution_id=uuid4(),
        last_processed_event_id=0,
        activity_definitions_map={},
        activity_index_map={},
        pending_activity_updates=updates,
        pending_sync_event_ids=pending,
    )


async def test_pending_events_processed_in_ascending_event_order() -> None:
    """Updates apply in ascending event-id order regardless of set insertion order."""
    # Values chosen so raw set-iteration order ([16, 1, 2]) differs from sorted
    # order ([1, 2, 16]) in CPython, so this fails if the sort is reverted.
    updates = {16: {"_eid": 16}, 1: {"_eid": 1}, 2: {"_eid": 2}}
    pending = {16, 1, 2}
    assert list(pending) != sorted(pending)  # guard: raw set order is not ascending
    metadata = _metadata(updates, pending)
    host = _FakeHost()

    await ActivityExecutionSynchronizer(host).sync(metadata, Mock())

    assert host.processed == [1, 2, 16]
    assert metadata.pending_sync_event_ids == set()  # cleared on success


async def test_mixed_subworkflow_and_ordinary_events_share_one_order() -> None:
    """Sub-workflow setup and ordinary activity updates are ordered identically."""
    updates = {
        205: {"_eid": 205, "_subworkflow_setup": 1},
        101: {"_eid": 101},
        150: {"_eid": 150, "_subworkflow_setup": 1},
        102: {"_eid": 102},
    }
    pending = set(updates)
    assert list(pending) != sorted(pending)
    metadata = _metadata(updates, pending)
    host = _FakeHost()

    await ActivityExecutionSynchronizer(host).sync(metadata, Mock())

    assert host.processed == [101, 102, 150, 205]


async def test_many_for_each_iterations_apply_latest_last() -> None:
    """With many iterations the highest event id is applied last (deterministic winner)."""
    updates = {eid: {"_eid": eid, "_subworkflow_setup": 1} for eid in (40, 12, 88, 7, 63)}
    pending = set(updates)
    assert list(pending) != sorted(pending)
    metadata = _metadata(updates, pending)
    host = _FakeHost()

    await ActivityExecutionSynchronizer(host).sync(metadata, Mock())

    assert host.processed == [7, 12, 40, 63, 88]
    assert host.processed[-1] == max(updates)  # latest iteration wins
