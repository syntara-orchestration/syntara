"""Handlers delegate, validate flat inputs and use workflow permission helpers."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.models.responses import (
    EventSubscriptionListResponse,
    EventSubscriptionRead,
    EventSubscriptionTestResponse,
)
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.router import _read, _update, get_inspection_service, router
from syntara.eventstreams.services.inspection_service import EventSubscriptionInspectionService


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


@pytest.mark.parametrize("read_route", ["list", "detail"])
@pytest.mark.parametrize("partition_ids", [None, [0, 2, 5]], ids=["legacy", "captured"])
def test_read_routes_preserve_initial_partition_set(
    client: TestClient, service: AsyncMock, read_route: str, partition_ids: list[int] | None
) -> None:
    """Real shaping and HTTP serialization preserve captured sets and missing legacy data."""
    stored_configuration = {"transport": "kafka", "topic": "alerts", "group_id": "syntara.test"}
    configuration = KafkaSourceConfiguration.model_validate(
        stored_configuration
        if partition_ids is None
        else {**stored_configuration, "initial_partition_ids": partition_ids}
    )
    subscription = EventSubscription(
        workflow_id=uuid4(),
        project_id=uuid4(),
        trigger_node_id="incoming",
        published_version_id=uuid4(),
        active_source_generation=1,
        configuration_revision=1,
        created_by=uuid4(),
    )
    integration_id = uuid4()
    source = EventSubscriptionSource(
        subscription_id=subscription.id,
        deployment_id=uuid4(),
        generation=1,
        integration_id=integration_id,
        integration_identity=integration_id,
        transport="kafka",
        configuration=configuration,
    )
    shaped = EventSubscriptionInspectionService._shape(subscription, source)
    service.get_current.return_value = shaped
    service.list_current.return_value = EventSubscriptionListResponse(resources=[shaped])
    url = f"/api/v1/workflows/{subscription.workflow_id}/event-subscriptions"

    response = client.get(url if read_route == "list" else f"{url}/{subscription.id}")

    assert response.status_code == 200, response.text
    resource = response.json()["resources"][0] if read_route == "list" else response.json()
    assert resource["source"]["configuration"] == {
        **stored_configuration,
        "cluster_id": None,
        "topic_id": None,
        "initial_partition_ids": partition_ids,
    }
    assert EventSubscriptionRead.model_validate(resource) == shaped


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
        {"initial_partition_ids": [0, 2, 5]},
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


@pytest.mark.parametrize("cert_authenticated", [False, True])
def test_inspection_service_preserves_request_authentication_context(*, cert_authenticated: bool) -> None:
    request = Request({"type": "http", "state": {"is_cert_authenticated": cert_authenticated}})
    instance = get_inspection_service(MagicMock(), MagicMock(), MagicMock(), request)
    assert instance.workflows.is_cert_authenticated is cert_authenticated
    assert instance.controls.workflows.is_cert_authenticated is cert_authenticated
