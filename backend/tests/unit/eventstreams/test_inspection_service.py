"""Scoped inspection, reference authorization and no-write preflight evidence."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.exceptions import EventSubscriptionNotFoundError
from syntara.eventstreams.models.responses import EventSubscriptionListParams, EventSubscriptionTestResponse
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.inspection_service import EventSubscriptionInspectionService
from syntara.integrations.models.integration_configuration import KafkaConfiguration

MODULE = "syntara.eventstreams.services.inspection_service"

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Dialect


async def test_detail_shapes_only_configuration_and_current_source(service: EventSubscriptionInspectionService) -> None:
    workflow = cast("MagicMock", service.workflows).get_workflow_by_id.return_value
    subscription = EventSubscription(
        workflow_id=workflow.id,
        project_id=workflow.project_id,
        trigger_node_id="incoming",
        published_version_id=uuid4(),
        active_source_generation=2,
        configuration_revision=3,
        created_by=uuid4(),
        runtime_credential_id=uuid4(),
        input_schema={"type": "object"},
    )
    integration_id = uuid4()
    source = EventSubscriptionSource(
        subscription_id=subscription.id,
        deployment_id=uuid4(),
        generation=2,
        integration_id=integration_id,
        integration_identity=integration_id,
        transport="kafka",
        configuration=KafkaSourceConfiguration(topic="alerts", group_id="generated"),
    )
    result = MagicMock()
    result.one_or_none.return_value = (subscription, source)
    cast("AsyncMock", service.session).exec.return_value = result
    response = await service.get_current(workflow.id, subscription.id)
    assert response.id == subscription.id
    assert response.source.id == source.id
    assert response.source.generation == 2
    assert response.source.configuration.topic == "alerts"
    assert response.runtime_credential_id == subscription.runtime_credential_id
    assert set(response.model_dump()) == {
        "id",
        "workflow_id",
        "project_id",
        "trigger_node_id",
        "published_version_id",
        "configuration_revision",
        "runtime_credential_id",
        "input_schema",
        "desired_enabled",
        "paused",
        "created_at",
        "updated_at",
        "source",
    }


@pytest.fixture
def service() -> EventSubscriptionInspectionService:
    """Request services with strictly mocked database and resource boundaries."""
    instance = EventSubscriptionInspectionService(AsyncMock(), MagicMock(), MagicMock(), MagicMock())
    instance.workflows = MagicMock()
    instance.workflows.get_workflow_by_id = AsyncMock(return_value=SimpleNamespace(id=uuid4(), project_id=uuid4()))
    instance.workflows.validate_event_subscribe_access = AsyncMock()
    instance.integrations = MagicMock()
    instance.integrations._resolve_credential = AsyncMock(
        return_value={"kafka_username": "runtime", "kafka_password": "secret"}
    )
    return instance


async def test_preflight_uses_only_selected_runtime_credential(service: EventSubscriptionInspectionService) -> None:
    params = KafkaSubscribeParameters(transport="kafka", topic="alerts", integration_id=uuid4(), credential_id=uuid4())
    integration = SimpleNamespace(
        configuration=KafkaConfiguration(bootstrap_servers=["broker.example.com:9093"]),
        management_credential_id=uuid4(),
    )
    cast("AsyncMock", service.session).get.return_value = integration
    response = EventSubscriptionTestResponse(success=True, checked_at="2026-10-19T00:00:00Z")
    with patch(f"{MODULE}.test_kafka_connection", return_value=response) as probe:
        assert await service.test_unsaved(uuid4(), params) is response
    workflow = cast("MagicMock", service.workflows).get_workflow_by_id.return_value
    cast("MagicMock", service.workflows).validate_event_subscribe_access.assert_awaited_once_with(
        params.model_dump(mode="json"), workflow.project_id
    )
    cast("MagicMock", service.integrations)._resolve_credential.assert_awaited_once_with(params.credential_id)
    assert probe.call_args.args[1]["kafka_username"] == "runtime"
    for method in ("add", "flush", "commit", "delete"):
        getattr(cast("AsyncMock", service.session), method).assert_not_called()


async def test_denied_reference_never_decrypts_or_connects(service: EventSubscriptionInspectionService) -> None:
    params = KafkaSubscribeParameters(transport="kafka", topic="alerts", integration_id=uuid4(), credential_id=uuid4())
    cast("MagicMock", service.workflows).validate_event_subscribe_access.side_effect = AuthorizationDeniedError(
        "Denied"
    )
    with patch(f"{MODULE}.test_kafka_connection") as probe, pytest.raises(AuthorizationDeniedError):
        await service.test_unsaved(uuid4(), params)
    cast("MagicMock", service.integrations)._resolve_credential.assert_not_called()
    probe.assert_not_called()


async def test_detail_query_enforces_parent_project_and_current_source(
    service: EventSubscriptionInspectionService,
) -> None:
    result = MagicMock()
    result.one_or_none.return_value = None
    cast("AsyncMock", service.session).exec.return_value = result
    with pytest.raises(EventSubscriptionNotFoundError):
        await service.get_current(uuid4(), uuid4())
    query: Any = cast("AsyncMock", service.session).exec.call_args.args[0]
    dialect = cast("Callable[[], Dialect]", postgresql.dialect)()
    sql = str(query.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    workflow = cast("MagicMock", service.workflows).get_workflow_by_id.return_value
    assert str(workflow.id) in sql
    assert str(workflow.project_id) in sql
    assert "event_subscriptions.retired IS false" in sql
    assert "event_subscription_sources.retired_at IS NULL" in sql
    assert "event_subscription_sources.generation = event_subscriptions.active_source_generation" in sql


async def test_list_scope_applies_to_rows_total_and_cursor_checks(service: EventSubscriptionInspectionService) -> None:
    """Exercise BaseService pagination/count rather than mock its delegation."""
    result = MagicMock()
    result.all.return_value = []
    result.one.return_value = 0
    cast("AsyncMock", service.session).exec.return_value = result
    params = EventSubscriptionListParams(limit=2, include_total=True, transport="kafka")
    response = await service.list_current(
        uuid4(), params, [("workflow_id[in]", str(uuid4())), ("retired", "true"), ("transport", "kafka")]
    )
    assert response.resources == []
    assert response.total == 0
    assert response.next is response.prev is None
    dialect = cast("Callable[[], Dialect]", postgresql.dialect)()
    queries = [
        str(cast("Any", c.args[0]).compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
        for c in cast("AsyncMock", service.session).exec.call_args_list
    ]
    assert len(queries) >= 2
    workflow = cast("MagicMock", service.workflows).get_workflow_by_id.return_value
    for sql in queries:
        assert str(workflow.id) in sql
        assert str(workflow.project_id) in sql
        assert "event_subscriptions.retired IS false" in sql
        assert "event_subscription_sources.transport = 'kafka'" in sql
    assert "LIMIT 3" in queries[0]
