"""Handlers delegate, validate flat inputs and use workflow permission helpers."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from syntara.eventstreams.models.responses import EventSubscriptionTestResponse
from syntara.eventstreams.router import _read, _update, get_inspection_service, router


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
    app.dependency_overrides[_read] = lambda: None
    app.dependency_overrides[_update] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "transport=other"])
def test_list_rejects_invalid_bounds(client: TestClient, service: AsyncMock, query: str) -> None:
    assert client.get(f"/api/v1/workflows/{uuid4()}/event-subscriptions?{query}").status_code == 422
    service.list_current.assert_not_called()


def test_unsaved_flat_request_delegates(client: TestClient, service: AsyncMock) -> None:
    workflow_id = uuid4()
    data = {"topic": "alerts", "integration_id": str(uuid4()), "credential_id": str(uuid4())}
    response = client.post(f"/api/v1/workflows/{workflow_id}/event-subscriptions/test", json=data)
    assert response.status_code == 200
    assert response.json()["topic_read"] == response.json()["group_access"] == "unverified"
    assert service.test_unsaved.call_args.args[0] == workflow_id
    assert service.test_unsaved.call_args.args[1].model_dump(mode="json") == {**data, "input_schema": None}


@pytest.mark.parametrize(
    "change",
    [
        {"selected_account_id": str(uuid4())},
        {"source": {"topic": "alerts"}},
        {"transport": "kafka"},
        {"credential_id": None},
    ],
)
def test_unsaved_rejects_invalid_or_selected_account_fields(
    client: TestClient, service: AsyncMock, change: dict[str, Any]
) -> None:
    data = {"topic": "alerts", "integration_id": str(uuid4()), "credential_id": str(uuid4())}
    response = client.post(f"/api/v1/workflows/{uuid4()}/event-subscriptions/test", json={**data, **change})
    assert response.status_code == 422
    service.test_unsaved.assert_not_called()
