"""Database fixtures for delivery repository and retained-evidence integration tests."""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import PropertyMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import Settings, get_settings
from syntara.core.models.principal import Principal, service_principal_id
from syntara.core.models.user import User
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.core.deduplication import (
    DeliveryClaim,
    DeliveryExpectation,
    DeliveryIdentity,
    DeliveryRepository,
    FrozenDeliveryBinding,
    input_fingerprint,
)
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.subscription_service import EventSubscriptionService
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion


@pytest.fixture(autouse=True)
def _delivery_service_identity() -> Generator[None, None, None]:
    """Match workflow integration tests that run without S2S TLS certificates."""
    with patch.object(Settings, "service_identity", new_callable=PropertyMock, return_value="backend.ao.svc"):
        yield


class AvailableCapacity:
    """Test double isolating claims from the separately tested capacity measurement."""

    async def permits_new_delivery(self) -> bool:
        """Allow small fixture datasets without changing production thresholds."""
        return True


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

    def expectation(self) -> DeliveryExpectation:
        """Return the immutable upstream publication expectation."""
        return DeliveryExpectation(
            published_version_id=self.snapshot.published_version_id,
            configuration_revision=self.snapshot.configuration_revision,
        )

    def store(self, session: AsyncSession) -> DeliveryRepository[Execution]:
        """Use the real repository and platform principal with only capacity isolated."""
        return EventDeliveryStore(session, capacity_check=AvailableCapacity())

    async def claim(self, offset: int = 0, *, owner: str = "first", prepare: bool = False) -> DeliveryClaim:
        """Commit a claim and optional Execution preparation together."""
        identity = self.identity(offset)
        async with self.session_factory() as session, session.begin():
            store = self.store(session)
            result = await store.acquire(identity, self.expectation(), owner)
            if not isinstance(result, DeliveryClaim):
                msg = f"Fixture claim was not acquired: {type(result).__name__}"
                raise TypeError(msg)
            if not prepare:
                return result
            now: datetime = (await session.exec(select(func.clock_timestamp()))).one()
            input_data = {"payload": {"offset": str(offset)}}
            context = {"workflow_context": {"created_by": "workflow-author"}}
            binding = FrozenDeliveryBinding(
                workflow_version_id=self.snapshot.published_version_id,
                configuration_revision=self.snapshot.configuration_revision,
                runtime_credential_id=self.snapshot.runtime_credential_id,
                connection_revision="connection-1",
                execution_principal_id=self.principal_id,
                enabled_by=self.snapshot.enabled_by,
                received_at=now,
                prepared_at=now,
                input_fingerprint=input_fingerprint(input_data, context),
            )
            execution = Execution(
                id=identity.execution_id,
                workflow_id=identity.workflow_id,
                workflow_version_id=binding.workflow_version_id,
                project_id=self.snapshot.project_id,
                trigger_node_id=self.snapshot.trigger_node_id,
                temporal_workflow_id=identity.temporal_workflow_id,
                input_data=input_data,
                execution_metadata=context,
                created_by=self.principal_id,
                updated_by=self.principal_id,
                created_at=now,
                updated_at=now,
            )
            frozen = await store.freeze(result, binding, execution)
            if not isinstance(frozen, DeliveryClaim):
                msg = f"Fixture preparation failed: {type(frozen).__name__}"
                raise TypeError(msg)
            return frozen

    async def expire(self, claim: DeliveryClaim) -> None:
        """Advance only the test lease to exercise takeover without sleeping."""
        async with self.session_factory() as session, session.begin():
            await session.execute(
                update(EventDelivery)
                .where(col(EventDelivery.identity_digest) == claim.identity.digest)
                .values(lease_until=func.clock_timestamp() - timedelta(seconds=1))
            )


@pytest_asyncio.fixture
async def delivery_context(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> DeliveryContext:
    """Project a published trigger through AAP-94316 before testing delivery storage."""
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
                        "transport": "kafka",
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
