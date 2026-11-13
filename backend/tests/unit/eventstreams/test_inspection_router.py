"""Handlers delegate, validate flat inputs and use workflow permission helpers."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from syntara.eventstreams.models.responses import EventSubscriptionTestResponse
from syntara.eventstreams.router import _update, get_inspection_service, router


@pytest.fixture
def service() -> AsyncMock:
    """No database, credential or broker access from handler tests."""
    mock = AsyncMock()
    mock.test_unsaved.return_value = EventSubscriptionTestResponse(
        success=True, checked_at=datetime.now(UTC), connection="verified", topic_metadata="verified"
    )
    return mock


@pytest.fixture
def client(service: AsyncMock) -> TestClient:
    """Override permission execution but retain helper metadata for inspection."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    app.dependency_overrides[get_inspection_service] = lambda: service
    app.dependency_overrides[_update] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("GET", ""),
        ("GET", "/{subscription_id}"),
        ("POST", "/{subscription_id}/pause"),
        ("POST", "/{subscription_id}/resume"),
        ("POST", "/{subscription_id}/retry"),
        ("POST", "/{subscription_id}/recover"),
        ("POST", "/{subscription_id}/retire"),
    ],
)
def test_subscription_read_and_control_routes_are_absent(client: TestClient, method: str, suffix: str) -> None:
    suffix = suffix.format(subscription_id=uuid4())
    response = client.request(method, f"/api/v1/workflows/{uuid4()}/event_subscriptions{suffix}")
    assert response.status_code == 404


def test_only_connection_test_is_exposed_in_openapi(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    assert set(document["paths"]) == {"/api/v1/workflows/{workflow_id}/event_subscriptions/test"}


def test_unsaved_flat_request_delegates(client: TestClient, service: AsyncMock) -> None:
    workflow_id = uuid4()
    data = {"topic": "alerts", "integration_id": str(uuid4()), "credential_id": str(uuid4())}
    response = client.post(f"/api/v1/workflows/{workflow_id}/event_subscriptions/test", json=data)
    assert response.status_code == 200
    assert response.json()["topic_read"] == response.json()["group_access"] == "unverified"
    assert service.test_unsaved.call_args.args[0] == workflow_id
    assert service.test_unsaved.call_args.args[1].model_dump(mode="json") == {
        **data,
        "input_schema": None,
        "filter": None,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"selected_account_id": str(uuid4())},
        {"source": {"topic": "alerts"}},
        {"transport": "kafka"},
        {"initial_partition_ids": [0, 2, 5]},
        {"credential_id": None},
    ],
)
def test_unsaved_rejects_invalid_or_selected_account_fields(
    client: TestClient, service: AsyncMock, change: dict[str, Any]
) -> None:
    data = {"topic": "alerts", "integration_id": str(uuid4()), "credential_id": str(uuid4())}
    response = client.post(f"/api/v1/workflows/{uuid4()}/event_subscriptions/test", json={**data, **change})
    assert response.status_code == 422
    service.test_unsaved.assert_not_called()


@pytest.mark.parametrize("cert_authenticated", [False, True])
def test_inspection_service_preserves_request_authentication_context(*, cert_authenticated: bool) -> None:
    request = Request({"type": "http", "state": {"is_cert_authenticated": cert_authenticated}})
    instance = get_inspection_service(MagicMock(), MagicMock(), MagicMock(), request)
    assert instance.workflows.is_cert_authenticated is cert_authenticated
