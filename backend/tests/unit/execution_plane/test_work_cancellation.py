"""Unit tests for Execution Plane work-item cancellation."""

from typing import Self
from unittest.mock import patch
from uuid import UUID, uuid4, uuid5

import pytest

from syntara.execution_plane.cancellation import (
    cancel_execution_plane_work_items,
)
from syntara.execution_plane.client import ExecutionPlaneRejectedError
from syntara.execution_plane.utils import execution_plane_work_item_id


class _FakeExecutionPlaneClient:
    def __init__(self, failures: dict[UUID, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.cancelled: list[UUID] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def cancel_work_item(self, *, work_item_id: UUID) -> None:
        failure = self.failures.get(work_item_id)
        if failure is not None:
            raise failure
        self.cancelled.append(work_item_id)


def test_work_item_identity_matches_dispatch_strategy() -> None:
    execution_id = uuid4()
    activity_id = "script-node"

    assert execution_plane_work_item_id(execution_id, activity_id) == uuid5(execution_id, activity_id)


@pytest.mark.asyncio
async def test_cancellation_uses_deterministic_work_item_ids() -> None:
    execution_id = uuid4()
    client = _FakeExecutionPlaneClient()

    with patch("syntara.execution_plane.cancellation.ExecutionPlaneHttpClient", return_value=client):
        cancelled = await cancel_execution_plane_work_items(execution_id, ["script-node", "other-script"])

    assert cancelled == [uuid5(execution_id, "script-node"), uuid5(execution_id, "other-script")]
    assert client.cancelled == cancelled


@pytest.mark.asyncio
async def test_cancellation_continues_after_one_work_item_fails() -> None:
    execution_id = uuid4()
    first_id = uuid5(execution_id, "first")
    second_id = uuid5(execution_id, "second")
    client = _FakeExecutionPlaneClient(
        {
            first_id: ExecutionPlaneRejectedError(
                "Execution Plane work item not found",
                status_code=404,
            )
        }
    )

    with patch("syntara.execution_plane.cancellation.ExecutionPlaneHttpClient", return_value=client):
        cancelled = await cancel_execution_plane_work_items(execution_id, ["first", "second"])

    assert cancelled == [second_id]
    assert client.cancelled == [second_id]
