"""Publication preserves captured source evidence without broker/worker calls."""

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.subscription_service import EventSubscriptionService
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion


@pytest.mark.parametrize("replacement", [None, "topic", "integration"])
async def test_publication_preserves_or_isolates_captured_source(replacement: str | None) -> None:
    user = User(id=uuid4(), username="publisher")
    session = AsyncMock(spec=AsyncSession)
    service = EventSubscriptionService(session, user)
    deployment_id = uuid4()
    integration = Integration(
        integration_type=IntegrationType.KAFKA,
        name="kafka",
        configuration=KafkaConfiguration(integration_type="kafka", bootstrap_servers=["broker:9092"]),
        created_by=user.id,
    )
    subscription = EventSubscription(
        workflow_id=uuid4(),
        project_id=uuid4(),
        trigger_node_id="incoming",
        published_version_id=uuid4(),
        active_source_generation=1,
        configuration_revision=1,
        runtime_credential_id=uuid4(),
        desired_enabled=False,
        created_by=user.id,
    )
    configuration = KafkaSourceConfiguration(
        topic="orders",
        group_id=f"syntara.{deployment_id}.{subscription.id}.1",
        cluster_id="verified-cluster",
        topic_id="verified-topic",
        initial_partition_ids=(0, 2, 5),
    )
    source = EventSubscriptionSource(
        subscription_id=subscription.id,
        deployment_id=deployment_id,
        generation=1,
        integration_id=integration.id,
        integration_identity=integration.id,
        transport="kafka",
        configuration=configuration,
        initialized_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    if replacement == "integration":
        integration.id = uuid4()
    parameters = KafkaSubscribeParameters(
        integration_id=integration.id,
        credential_id=subscription.runtime_credential_id,
        topic="replacement" if replacement == "topic" else "orders",
        input_schema={"type": "object"},
    )
    version = WorkflowVersion(
        workflow_id=subscription.workflow_id,
        version=2,
        schema_version="2.0.0",
        workflow_definition={},
        created_by=user.id,
    )

    with (
        patch.object(service, "_get_source", new=AsyncMock(return_value=source)),
        patch.object(service, "_next_generation", new=AsyncMock(return_value=2)),
    ):
        snapshot = await service._update_subscription(subscription, version, integration, parameters, deployment_id)

    assert snapshot.published_version_id == version.id
    assert snapshot.desired_enabled is True
    assert snapshot.configuration_revision == 2
    assert snapshot.input_schema == {"type": "object"}
    assert source.configuration == configuration
    if replacement is None:
        session.add.assert_not_called()
        assert snapshot.source_id == source.id
        assert snapshot.configuration == configuration
        assert source.retired_at is None
        assert source.initialized_at == datetime(2026, 1, 1, tzinfo=UTC)
    else:
        new_source = session.add.call_args.args[0]
        assert isinstance(new_source, EventSubscriptionSource)
        assert new_source.id != source.id
        assert source.retired_at is not None
        assert snapshot.source_generation == 2
        assert snapshot.configuration.group_id == f"syntara.{deployment_id}.{subscription.id}.2"
        assert snapshot.configuration.initial_partition_ids is None
        assert snapshot.configuration.cluster_id is None
        assert snapshot.configuration.topic_id is None
        assert new_source.initialized_at is None
    session.flush.assert_awaited_once()


async def test_invalid_later_binding_never_changes_projection() -> None:
    user = User(id=uuid4(), username="publisher")
    session = AsyncMock(spec=AsyncSession)
    service = EventSubscriptionService(session, user)
    integration = Integration(
        name="kafka",
        integration_type=IntegrationType.KAFKA,
        configuration=KafkaConfiguration(integration_type="kafka", bootstrap_servers=["broker:9092"]),
        created_by=user.id,
    )
    parameters = KafkaSubscribeParameters(integration_id=integration.id, credential_id=uuid4(), topic="orders")
    workflow = Workflow(name="workflow", project_id=uuid4(), created_by=user.id)
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        created_by=user.id,
        workflow_definition={
            "triggers": [
                {"id": node_id, "type": "event_subscribe_trigger", "parameters": {}} for node_id in ("first", "second")
            ]
        },
    )
    with (
        patch.object(service, "lock_workflow_subscriptions", new=AsyncMock(return_value=[])),
        patch.object(service, "_get_deployment_id", new=AsyncMock(return_value=uuid4())),
        patch.object(
            service,
            "_resolve_binding",
            new=AsyncMock(side_effect=[(integration, parameters), SafeValueError("invalid second binding")]),
        ),
    ):
        with pytest.raises(SafeValueError, match="invalid second binding"):
            await service.sync_from_published_definition(workflow, version, enabled=True)

    session.add.assert_not_called()
    session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_persistence_and_projection_modules_have_no_runtime_client_imports() -> None:
    for model in (
        EventConsumerWorker,
        EventSubscription,
        EventSubscriptionSource,
        KafkaSourceConfiguration,
        SubscriptionSnapshot,
        EventSubscriptionService,
    ):
        tree = ast.parse(Path(inspect.getfile(model)).read_text())
        imports = [
            node.module if isinstance(node, ast.ImportFrom) else alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        assert not any(name and name.startswith(("aiokafka", "kafka", "temporalio")) for name in imports)
