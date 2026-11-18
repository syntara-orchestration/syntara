"""Effective consumer groups come from current source generations, not saved drafts."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.workflows.services.kafka_subscription_sources import read_kafka_subscription_sources


@pytest.mark.asyncio
async def test_reads_effective_group_and_identity_without_payload_or_credentials() -> None:
    session = AsyncMock()
    workflow_id, source_id, integration_id = uuid4(), uuid4(), uuid4()
    subscription = MagicMock(trigger_node_id="subscribe", configuration_revision=7)
    source = MagicMock(
        id=source_id,
        generation=3,
        integration_identity=integration_id,
        configuration=KafkaSourceConfiguration(topic="orders", group_id="established-custom-group"),
    )
    session.exec.return_value = [(subscription, source)]

    result = await read_kafka_subscription_sources(session, workflow_id)

    assert [item.model_dump(mode="json") for item in result] == [
        {
            "trigger_node_id": "subscribe",
            "source_id": str(source_id),
            "generation": 3,
            "configuration_revision": 7,
            "integration_id": str(integration_id),
            "topic": "orders",
            "group_id": "established-custom-group",
        }
    ]
    statement = session.exec.call_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert workflow_id.hex in sql.replace("-", "")
    assert "event_subscriptions.retired IS false" in sql
    assert "event_subscription_sources.generation = event_subscriptions.active_source_generation" in sql
    assert "workflow_versions" not in sql
    # Unpublishing must not hide the projection that owns the fixed group.
    assert "desired_enabled =" not in sql


@pytest.mark.asyncio
async def test_new_workflow_has_no_established_groups() -> None:
    session = AsyncMock()
    session.exec.return_value = []

    assert await read_kafka_subscription_sources(session, uuid4()) == []


@pytest.mark.asyncio
async def test_detail_response_exposes_effective_group_even_when_definition_omits_it() -> None:
    from datetime import UTC, datetime
    from unittest.mock import patch

    from syntara.workflows.models.workflow import KafkaSubscriptionSourceRead, WorkflowRead
    from syntara.workflows.models.workflow_version import WorkflowVersionRead
    from syntara.workflows.router import _build_workflow_with_version_response

    workflow_id, version_id, project_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    workflow = MagicMock(id=workflow_id, published_version_id=None)
    version = MagicMock(id=version_id)
    service = AsyncMock()
    service.to_read.return_value = WorkflowRead(
        id=workflow_id,
        name="Orders",
        project_id=project_id,
        current_version=5001,
        is_enabled=False,
        created_at=now,
        updated_at=now,
    )
    service.get_publish_context.return_value = (set(), {})
    service.to_version_read.return_value = WorkflowVersionRead(
        id=version_id,
        workflow_id=workflow_id,
        version=5001,
        schema_version="2.0.0",
        workflow_definition={"triggers": [{"id": "subscribe", "parameters": {"group_id": None}}]},
        created_at=now,
        updated_at=now,
    )
    source = KafkaSubscriptionSourceRead(
        trigger_node_id="subscribe",
        source_id=uuid4(),
        generation=4,
        configuration_revision=7,
        integration_id=uuid4(),
        topic="orders",
        group_id="established-custom-group",
    )
    with patch("syntara.workflows.router.read_kafka_subscription_sources", AsyncMock(return_value=[source])) as read:
        response = await _build_workflow_with_version_response(workflow, version, service)

    read.assert_awaited_once_with(service.session, workflow_id)
    assert response.kafka_subscription_sources == [source]
    assert response.version.workflow_definition["triggers"][0]["parameters"]["group_id"] is None
