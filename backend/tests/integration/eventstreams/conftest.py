"""Published Kafka resources and normal Execution integration fixtures."""

from collections.abc import AsyncIterator, Generator
from dataclasses import dataclass
from unittest.mock import PropertyMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import Settings, get_settings
from syntara.core.models.principal import Principal, service_principal_id
from syntara.core.models.user import User
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.core.deduplication import DeliveryIdentity
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.subscription_service import EventSubscriptionService, lock_source_lifecycle
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion


@pytest.fixture(autouse=True)
def _delivery_service_identity() -> Generator[None, None, None]:
    """Match workflow integration tests that run without S2S TLS certificates."""
    with patch.object(Settings, "service_identity", new_callable=PropertyMock, return_value="backend.ao.svc"):
        yield


@dataclass
class DeliveryContext:
    """Committed upstream resources and fresh per-operation session factory."""

    snapshot: SubscriptionSnapshot
    principal_id: UUID
    session_factory: async_sessionmaker[AsyncSession]

    def identity(self, offset: int = 0) -> DeliveryIdentity:
        """Bind a Kafka coordinate to the actual persisted deployment/source scope."""
        return DeliveryIdentity(
            deployment_id=self.snapshot.deployment_id,
            integration_identity=self.snapshot.integration_identity,
            source_id=self.snapshot.source_id,
            source_generation=self.snapshot.source_generation,
            workflow_id=self.snapshot.workflow_id,
            subscription_id=self.snapshot.subscription_id,
            record=KafkaRecordIdentity(topic=self.snapshot.configuration.topic, partition=0, offset=offset),
        )


async def hold_partition_recovery(context: DeliveryContext, partition: int = 0) -> UUID:
    """Arrange a committed partition fence for integration tests without broker I/O."""
    async with context.session_factory() as session, session.begin():
        lifecycle = await lock_source_lifecycle(session, context.snapshot.source_id)
        assert lifecycle is not None
        _, source = lifecycle
        row = await session.get(KafkaPartitionInitialPosition, (source.id, partition), with_for_update=True)
        now = (await session.exec(select(func.clock_timestamp()))).one()
        if row is None:
            row = KafkaPartitionInitialPosition(source_id=source.id, partition=partition, initial_next_offset=0)
            session.add(row)
        assert row.recovery_token is None
        token = uuid4()
        row.recovery_token = token
        row.recovery_revision += 1
        row.gap_detected_at = now
        row.gap_reason = "missing_commit"
        row.pending_boundary = 0
        row.pending_policy = "retained_beginning"
        row.pending_reason = "missing_commit"
    return token


async def finish_partition_recovery(context: DeliveryContext, partition: int, token: UUID) -> bool:
    """Arrange confirmation only for the matching test token, retaining other partitions."""
    async with context.session_factory() as session, session.begin():
        lifecycle = await lock_source_lifecycle(session, context.snapshot.source_id)
        assert lifecycle is not None
        _, source = lifecycle
        row = await session.get(KafkaPartitionInitialPosition, (source.id, partition), with_for_update=True)
        if row is None or row.recovery_token != token:
            return False
        row.recovery_boundary = row.pending_boundary
        row.recovery_policy = row.pending_policy
        row.recovery_reason = row.pending_reason
        row.duplicate_risk_acknowledged = row.pending_duplicate_risk_acknowledged
        row.recovery_confirmed_at = (await session.exec(select(func.clock_timestamp()))).one()
        row.recovery_token = None
        row.pending_boundary = None
        row.pending_policy = None
        row.pending_reason = None
        row.pending_duplicate_risk_acknowledged = False
        row.gap_detected_at = None
        row.gap_reason = None
    return True


@pytest_asyncio.fixture
async def delivery_context(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> DeliveryContext:
    """Project a published trigger before testing event handoff."""
    integration = Integration(
        name=f"delivery-kafka-{uuid4().hex[:8]}",
        integration_type=IntegrationType.KAFKA,
        configuration=KafkaConfiguration(integration_type="kafka", bootstrap_servers=["broker:9092"]),
        enabled=True,
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    credential_type = CredentialType(
        name=f"delivery-type-{uuid4().hex[:8]}",
        inputs={"fields": [], "required": []},
        injectors={"extra_vars": {}, "env": {}, "file": {}},
        managed=True,
    )
    test_db_session.add(integration)
    test_db_session.add(credential_type)
    await test_db_session.flush()
    credential = Credential(
        name=f"delivery-credential-{uuid4().hex[:8]}",
        credential_type_id=credential_type.id,
        project_id=test_project_id,
        created_by=test_user.id,
        enabled=True,
    )
    workflow = Workflow(
        name=f"delivery-workflow-{uuid4().hex[:8]}",
        project_id=test_project_id,
        created_by=test_user.id,
        is_enabled=False,
        current_version=1,
    )
    test_db_session.add(credential)
    test_db_session.add(workflow)
    await test_db_session.flush()
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        created_by=test_user.id,
        workflow_definition={
            "schema_version": "2.0.0",
            "name": workflow.name,
            "nodes": [],
            "edges": [],
            "triggers": [
                {
                    "id": "incoming",
                    "type": "event_subscribe_trigger",
                    "parameters": {
                        "integration_id": str(integration.id),
                        "credential_id": str(credential.id),
                        "topic": "orders",
                    },
                }
            ],
        },
    )
    test_db_session.add(version)
    await test_db_session.flush()
    changes = await EventSubscriptionService(test_db_session, test_user).sync_from_published_definition(
        workflow,
        version,
        enabled=True,
    )
    workflow.published_version_id = version.id
    workflow.is_enabled = True
    principal_id = service_principal_id(get_settings().service_identity)
    if await test_db_session.get(Principal, principal_id) is None:
        test_db_session.add(Principal.for_service(get_settings().service_identity))
    await test_db_session.commit()
    return DeliveryContext(changes.created[0], principal_id, test_db_session_factory)


@pytest_asyncio.fixture
async def eventstream_migration_engine(
    delivery_context: DeliveryContext,
    test_db_engine: AsyncEngine,
    test_db_admin_url: URL,
) -> AsyncIterator[AsyncEngine]:
    """Run migration DDL as admin in the current worker's disposable database.

    Build the engine after delivery_context has restored and populated that
    database. Application sessions keep their existing restricted permissions.
    """
    engine = create_async_engine(test_db_admin_url.set(database=test_db_engine.url.database), poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()
