"""Exercise AO's EP callback using real shared command envelopes."""

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from execution_plane_client.commands.control import Completion
from execution_plane_client.protocol import ResourceReference
from fastapi import FastAPI, Request, Response

from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.execution_plane import bridge
from syntara.workflows.executions_router import get_temporal_execution_service


@pytest.fixture
def callback() -> tuple[FastAPI, AsyncMock, MagicMock]:
    app = FastAPI()
    app.include_router(bridge.router)
    session = AsyncMock()
    rows = MagicMock()
    rows.first.return_value = ("workflow-id", "activity-id")
    session.exec.return_value = rows
    temporal = AsyncMock()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_temporal_execution_service] = lambda: temporal

    @app.middleware("http")
    async def certificate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.is_cert_authenticated = True
        request.state.cert_cn = get_settings().ep_callback_service_cn
        return await call_next(request)

    return app, temporal, rows


def completion():
    work_id = uuid4()
    return Completion(
        status="succeeded",
        result={"output": {"stdout": "ok"}},
        resource=ResourceReference(kind="work_item", resource_id=work_id),
    ).to_message(
        source_id="execution-plane",
        destination_id="syntara-orchestration",
        client_id="syntara-orchestration",
        parent_command_id=work_id,
    )


def test_router_only_exposes_the_command_ingress():
    assert {route.path for route in bridge.router.routes} == {"/api/execution_plane/v1/commands"}


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled", "outcome_unknown"])
async def test_completion_command_resolves_temporal_activity_and_acknowledges(callback, outcome, monkeypatch):
    app, temporal, _ = callback
    message = completion()
    body = message.model_dump(mode="json")
    body["command"]["payload"]["status"] = outcome
    validate = MagicMock(wraps=Completion.model_validate)
    monkeypatch.setattr(Completion, "model_validate", validate)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["message_id"] == str(message.message_id)
    assert response.json()["received"] is True
    assert response.json()["resource"]["kind"] == "work_item"
    assert response.json()["resource"]["resource_id"] == str(message.command.parent_command_id)
    validate.assert_called_once()
    if outcome == "succeeded":
        temporal.complete_async_activity.assert_awaited_once_with(
            temporal_workflow_id="workflow-id", activity_id="activity-id", result={"output": {"stdout": "ok"}}
        )
    else:
        assert temporal.fail_async_activity.await_args.kwargs["error"].non_retryable
        if outcome == "outcome_unknown":
            assert (
                temporal.fail_async_activity.await_args.kwargs["error"].type == "ExecutionPlaneReconciliationRequired"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["source_id", "destination_id", "client_id"])
async def test_completion_rejects_wrong_participant(callback, field):
    app, temporal, _ = callback
    body = completion().model_dump(mode="json")
    target = body["scope"] if field == "client_id" else body
    target[field] = "other-service"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)
    assert response.status_code == 403
    temporal.complete_async_activity.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", ["parent", "resource", "resource_kind", "revision", "type", "unknown_type", "status", "result"]
)
async def test_completion_rejects_invalid_correlation_or_command(callback, invalid):
    app, temporal, _ = callback
    body = completion().model_dump(mode="json")
    command = body["command"]
    if invalid == "parent":
        command["parent_command_id"] = None
    elif invalid == "resource":
        command["payload"]["resource"]["resource_id"] = str(uuid4())
    elif invalid == "resource_kind":
        command["payload"]["resource"]["kind"] = "cluster"
    elif invalid == "status":
        command["payload"]["status"] = "running"
    elif invalid == "result":
        command["payload"]["result"] = []
    elif invalid == "unknown_type":
        command["command_type"] = "unknown.command"
    elif invalid == "revision":
        command["command_revision"] = 2
    else:
        command["command_type"] = "command.cancel"
        command["payload"] = {"target_command_id": str(uuid4())}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)
    assert response.status_code == 422
    temporal.complete_async_activity.assert_not_awaited()
    temporal.fail_async_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_missing_activity_remains_retryable(callback):
    app, _, rows = callback
    rows.first.return_value = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=completion().model_dump(mode="json"))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_completion_without_resource_uses_parent_command_id(callback):
    app, temporal, _ = callback
    message = completion()
    body = message.model_dump(mode="json")
    body["command"]["payload"].pop("resource")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://ao") as client:
        response = await client.post("/api/execution_plane/v1/commands", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["resource"]["kind"] == "work_item"
    assert response.json()["resource"]["resource_id"] == str(message.command.parent_command_id)
    temporal.complete_async_activity.assert_awaited_once()
