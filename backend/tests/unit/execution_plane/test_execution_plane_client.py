"""Contract tests for AO requests sent to the independent Execution Plane."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.execution_plane.client import ExecutionPlaneHttpClient


@pytest.mark.asyncio
async def test_cluster_binding_request_keeps_namespace_as_kubernetes_integration_config() -> None:
    client = object.__new__(ExecutionPlaneHttpClient)
    request = AsyncMock(return_value={"status": "pending"})
    object.__setattr__(client, "_request", request)

    await client.upsert_cluster_binding(
        source_integration_id=uuid4(),
        revision=3,
        name="workers",
        endpoint="https://cluster.example",
        namespace="ep-workers",
        credential="opaque-credential",
        project_ids=None,
        labels={"environment": "test"},
        enabled=True,
    )

    await_args = request.await_args
    assert await_args is not None
    body = await_args.kwargs["json_body"]
    assert body["namespace"] == "ep-workers"
    assert "placement" not in body
