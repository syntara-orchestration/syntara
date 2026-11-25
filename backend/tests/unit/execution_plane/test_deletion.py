"""Deletion requires an acknowledged bulk request and propagates failures."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.execution_plane import deletion
from syntara.execution_plane.client import ExecutionPlaneRejectedError, ExecutionPlaneUnavailableError
from syntara.execution_plane.exceptions import ExecutionPlaneDeletionError


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["project_id", "workflow_id", "execution_id"])
async def test_deletion_sends_one_filtered_command(monkeypatch, field):
    owner_id = uuid4()
    client = AsyncMock()
    client.__aenter__.return_value = client
    monkeypatch.setattr(deletion, "ExecutionPlaneHttpClient", lambda: client)
    await deletion.delete_execution_plane_work_items(owner_field=field, owner_id=owner_id)
    client.delete_work_items.assert_awaited_once()
    assert client.delete_work_items.call_args.kwargs["selector"].model_dump(exclude_none=True) == {
        "runtime_context": {field: str(owner_id)}
    }
    client.list_work_items.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ExecutionPlaneUnavailableError, ExecutionPlaneRejectedError])
async def test_deletion_does_not_hide_ep_failure(monkeypatch, error):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.delete_work_items.side_effect = error()
    monkeypatch.setattr(deletion, "ExecutionPlaneHttpClient", lambda: client)
    with pytest.raises(ExecutionPlaneDeletionError):
        await deletion.delete_execution_plane_work_items(owner_field="project_id", owner_id=uuid4())
