"""Source contract alignment and preflight authorization boundaries."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import yaml
from fastapi.encoders import jsonable_encoder
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.core.exceptions import SafeValueError
from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.models.responses import EventSubscriptionSourceRead
from syntara.eventstreams.models.control import EventSubscriptionRecovery, EventSubscriptionRuntime
from syntara.eventstreams.models.responses import EventSubscriptionListParams, EventSubscriptionListResponse
from syntara.eventstreams.services.inspection_service import EventSubscriptionInspectionService
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from tests.unit.eventstreams.test_deduplication_store import NOW
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription

MODULE = "syntara.eventstreams.services.inspection_service"


@pytest.mark.parametrize(
    "spec_path",
    [
        "syntara/schemas/workflows/v2/openapi.yaml",
        "syntara/schemas/openapi.yaml",
        "syntara/schemas/openapi-public.yaml",
        "syntara/schemas/openapi-public.json",
        "cli/orchestrator_cli/openapi.yaml",
    ],
)
def test_source_read_partition_set_schema_matches_provider(spec_path: str) -> None:
    """Every public contract exposes the inherited optional partition set."""
    runtime = jsonable_encoder(
        EventSubscriptionSourceRead.model_json_schema(
            mode="serialization", ref_template="#/components/schemas/{model}"
        ),
        exclude_none=True,
    )
    spec = Path(__file__).resolve().parents[3] / "src" / spec_path
    schemas = yaml.safe_load(spec.read_text())["components"]["schemas"]

    assert (
        schemas["EventSubscriptionSourceRead"]["properties"]["configuration"] == runtime["properties"]["configuration"]
    )
    assert (
        schemas["KafkaSourceConfiguration"]["properties"]["initial_partition_ids"]
        == runtime["$defs"]["KafkaSourceConfiguration"]["properties"]["initial_partition_ids"]
    )
    assert "initial_partition_ids" not in schemas["KafkaSourceConfiguration"]["required"]


@pytest.fixture
def service() -> EventSubscriptionInspectionService:
    """Request services with strictly mocked database and resource boundaries."""
    instance = EventSubscriptionInspectionService(AsyncMock(), MagicMock(), MagicMock(), MagicMock())
    instance.workflows = MagicMock()
    instance.workflows.get_workflow_by_id = AsyncMock(return_value=SimpleNamespace(id=uuid4(), project_id=uuid4()))
    instance.workflows.validate_event_subscribe_access = AsyncMock()
    return instance


async def test_denied_reference_never_decrypts_or_connects(service: EventSubscriptionInspectionService) -> None:
    params = KafkaSubscribeParameters(topic="alerts", integration_id=uuid4(), credential_id=uuid4())
    cast("MagicMock", service.workflows).validate_event_subscribe_access.side_effect = AuthorizationDeniedError(
        "Denied"
    )
    with (
        patch(f"{MODULE}.resolve_listener_kafka_login", new_callable=AsyncMock) as resolve,
        patch(f"{MODULE}.test_kafka_connection") as probe,
        pytest.raises(AuthorizationDeniedError),
    ):
        await service.test_unsaved(uuid4(), params)
    resolve.assert_not_called()
    probe.assert_not_called()


@pytest.mark.ssrf_enforced
async def test_rebound_broker_never_decrypts_or_connects(service: EventSubscriptionInspectionService) -> None:
    """Recheck a stored hostname whose DNS now points to a private address."""
    params = KafkaSubscribeParameters(topic="alerts", integration_id=uuid4(), credential_id=uuid4())
    config = KafkaConfiguration(bootstrap_servers=["broker.example.com:9093"])
    cast("AsyncMock", service.session).get.return_value = SimpleNamespace(configuration=config)
    with (
        patch(
            "syntara.integrations.lib.url_validation.get_settings",
            return_value=SimpleNamespace(integration_url_allowed_hosts=[]),
        ),
        patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("192.168.1.10", 9093))]),
        patch(f"{MODULE}.resolve_listener_kafka_login", new_callable=AsyncMock) as resolve,
        patch(f"{MODULE}.test_kafka_connection") as probe,
        pytest.raises(SafeValueError, match="bootstrap_servers must not resolve"),
    ):
        await service.test_unsaved(uuid4(), params)
    resolve.assert_not_called()
    probe.assert_not_called()


@pytest.mark.parametrize("status", ["applied", "paused", "lagging", "old_publication", "old_generation"])
async def test_list_populates_lifecycle_state_and_all_worker_convergence(service, monkeypatch, status):
    first = _subscription(active_source_generation=2, paused=status == "paused")
    second = _subscription(workflow_id=first.workflow_id, project_id=first.project_id)
    current, previous, other = _source(first, generation=2), _source(first), _source(second)
    previous.retired_at = NOW
    positions = [
        KafkaPartitionInitialPosition(source_id=previous.id, partition=0, initial_next_offset=2**60),
        KafkaPartitionInitialPosition(source_id=other.id, partition=1, initial_next_offset=9),
    ]
    request = EventSubscriptionRecovery(
        source_id=previous.id,
        partition=0,
        configuration_revision=1,
        expected_recovery_revision=0,
        policy="current_end",
        reason="offset_expired",
        requested_by=uuid4(),
    )
    participants = [
        EventSubscriptionRuntime(
            source_id=current.id,
            worker_id="current",
            configuration_revision=1,
            applied_revision=None if status == "lagging" else 1,
            applied_published_version_id=uuid4() if status == "old_publication" else first.published_version_id,
            stopped=status == "paused",
        ),
        EventSubscriptionRuntime(
            source_id=previous.id,
            worker_id="previous",
            configuration_revision=1,
            stopped=status != "old_generation",
        ),
        EventSubscriptionRuntime(
            source_id=other.id,
            worker_id="other",
            configuration_revision=1,
            applied_revision=1,
            applied_published_version_id=second.published_version_id,
        ),
    ]
    session = MagicMock(spec=AsyncSession)
    results = []
    for rows in ([previous, other, current], positions, [request], participants):
        result = MagicMock()
        result.all.return_value = rows
        results.append(result)
    session.exec.side_effect = results
    service.session = session
    service.controls.session = session
    service.workflows.get_workflow_by_id.return_value = SimpleNamespace(
        id=first.workflow_id, project_id=first.project_id
    )

    async def paginate(
        _model,
        response_type: type[EventSubscriptionListResponse],
        *,
        post_query_callback,
        response_type_converter,
        **_kwargs: object,
    ) -> EventSubscriptionListResponse:
        await post_query_callback([first, second])
        return response_type(resources=[response_type_converter(item) for item in [first, second]])

    monkeypatch.setattr(service, "list_resources", paginate)
    response = await service.list_current(first.workflow_id, EventSubscriptionListParams(), [])
    first_read, second_read = response.resources
    assert first_read.source.id == current.id
    assert [item.id for item in first_read.sources] == [previous.id, current.id]
    assert [item.id for item in second_read.sources] == [other.id]
    assert first_read.initialization[0].source_id == previous.id
    assert first_read.initialization[0].initial_next_offset == 2**60
    assert second_read.initialization[0].source_id == other.id
    assert first_read.recovery[0].source_id == previous.id
    assert second_read.recovery == []
    applied = status in {"applied", "paused"}
    assert first_read.convergence == ("applied" if applied else "pending")
    assert first_read.applied_revision == (1 if applied else None)
    assert second_read.convergence == "applied"
    assert second_read.applied_revision == 1
    assert "recovery_token" not in first_read.initialization[0].model_dump()
    assert session.exec.await_count == 4


async def test_empty_list_does_not_query_lifecycle_state(service, monkeypatch):
    async def paginate(
        _model, response_type: type[EventSubscriptionListResponse], *, post_query_callback, **_kwargs: object
    ) -> EventSubscriptionListResponse:
        await post_query_callback([])
        return response_type(resources=[])

    monkeypatch.setattr(service, "list_resources", paginate)
    response = await service.list_current(uuid4(), EventSubscriptionListParams(), [])
    assert response.resources == []
    service.session.exec.assert_not_awaited()
