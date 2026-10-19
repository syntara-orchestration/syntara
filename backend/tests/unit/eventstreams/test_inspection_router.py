"""Handlers delegate, validate flat inputs and use workflow permission helpers."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from syntara.eventstreams.error_handlers import event_subscription_not_found_handler
from syntara.eventstreams.exceptions import EventSubscriptionNotFoundError
from syntara.eventstreams.models.responses import EventSubscriptionListResponse, EventSubscriptionTestResponse
from syntara.eventstreams.router import _read, _update, get_inspection_service, router


@pytest.fixture
def service() -> AsyncMock:
    """No database, credential or broker access from handler tests."""
    mock = AsyncMock()
    mock.list_current.return_value = EventSubscriptionListResponse(resources=[], next=None, prev=None, total=None)
    mock.test_unsaved.return_value = EventSubscriptionTestResponse(
        success=True, checked_at=datetime.now(UTC), connection="verified", topic_metadata="verified"
    )
    return mock


@pytest.fixture
def client(service: AsyncMock) -> TestClient:
    """Override permission execution but retain helper metadata for inspection."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def not_found(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, EventSubscriptionNotFoundError)
        return event_subscription_not_found_handler(request, exc)

    app.add_exception_handler(EventSubscriptionNotFoundError, not_found)
    app.dependency_overrides[get_inspection_service] = lambda: service
    app.dependency_overrides[_read] = lambda: None
    app.dependency_overrides[_update] = lambda: None
    return TestClient(app)


def test_permission_helpers_are_workflow_read_and_update_only() -> None:
    assert (_read.resource_type, _read.action) == ("workflow", "read")
    assert (_update.resource_type, _update.action) == ("workflow", "update")
    assert _read.resource_id_param == _update.resource_id_param == "workflow_id"


def test_list_delegates_standard_bounds(client: TestClient, service: AsyncMock) -> None:
    workflow_id = uuid4()
    response = client.get(
        f"/api/v1/workflows/{workflow_id}/event-subscriptions?limit=5&transport=kafka&include_total=true"
    )
    assert response.status_code == 200
    args = service.list_current.call_args.args
    assert args[0] == workflow_id
    assert args[1].limit == 5
    assert args[1].transport == "kafka"
    assert args[1].include_total


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "transport=other"])
def test_list_rejects_invalid_bounds(client: TestClient, service: AsyncMock, query: str) -> None:
    assert client.get(f"/api/v1/workflows/{uuid4()}/event-subscriptions?{query}").status_code == 422
    service.list_current.assert_not_called()


def test_unsaved_flat_request_delegates(client: TestClient, service: AsyncMock) -> None:
    workflow_id = uuid4()
    data = {"transport": "kafka", "topic": "alerts", "integration_id": str(uuid4()), "credential_id": str(uuid4())}
    response = client.post(f"/api/v1/workflows/{workflow_id}/event-subscriptions/test", json=data)
    assert response.status_code == 200
    assert response.json()["topic_read"] == response.json()["group_access"] == "unverified"
    assert service.test_unsaved.call_args.args[0] == workflow_id
    assert service.test_unsaved.call_args.args[1].model_dump(mode="json") == {**data, "input_schema": None}


@pytest.mark.parametrize(
    "change",
    [
        {"execution_service_account_id": str(uuid4())},
        {"selected_account_id": str(uuid4())},
        {"group_id": "customer-group"},
        {"source": {"topic": "alerts"}},
        {"topic": "*"},
        {"topic": ".."},
        {"transport": "other"},
        {"credential_id": None},
    ],
)
def test_unsaved_rejects_invalid_or_selected_account_fields(
    client: TestClient, service: AsyncMock, change: dict[str, Any]
) -> None:
    data = {"transport": "kafka", "topic": "alerts", "integration_id": str(uuid4()), "credential_id": str(uuid4())}
    response = client.post(f"/api/v1/workflows/{uuid4()}/event-subscriptions/test", json={**data, **change})
    assert response.status_code == 422
    service.test_unsaved.assert_not_called()


def test_detail_delegation(client: TestClient, service: AsyncMock) -> None:
    workflow_id, subscription_id = uuid4(), uuid4()
    # An invalid service return deliberately fails response validation only after
    # the handler has delegated the correctly parsed parent and subscription IDs.
    service.get_current.side_effect = RuntimeError("delegated")
    with pytest.raises(RuntimeError, match="delegated"):
        client.get(f"/api/v1/workflows/{workflow_id}/event-subscriptions/{subscription_id}")
    service.get_current.assert_awaited_once_with(workflow_id, subscription_id)


def test_absent_retired_or_unrelated_subscription_uses_safe_problem(client: TestClient, service: AsyncMock) -> None:
    service.get_current.side_effect = EventSubscriptionNotFoundError()
    response = client.get(f"/api/v1/workflows/{uuid4()}/event-subscriptions/{uuid4()}")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "Event subscription not found"
