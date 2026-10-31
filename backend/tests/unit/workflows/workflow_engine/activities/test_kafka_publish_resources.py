"""Check Publish references against the same database scope used by other actions."""

from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.exceptions import ApplicationError

from syntara.core.models import User
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities.kafka_publish_connection import current_publish_resources
from syntara.workflows.workflow_engine.models.kafka_publish import KafkaPublishParameters


@pytest.mark.asyncio
async def test_project_scope_and_disabling_are_checked_without_management_fallback(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    config = KafkaConfiguration(
        bootstrap_servers=["broker.example.com:9092"], security_protocol="PLAINTEXT", allow_plaintext=True
    )
    integration = Integration(
        name=f"publish-{uuid4().hex}",
        integration_type=IntegrationType.KAFKA,
        configuration=config,
        scope=IntegrationScope.PROJECT,
        enabled=True,
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(integration)
    await test_db_session.flush()
    parameters = KafkaPublishParameters(integration_id=str(integration.id), topic="outcomes", payload=None)
    with pytest.raises(ApplicationError) as error:
        await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert error.value.non_retryable
    test_db_session.add(IntegrationProjectAssignment(integration_id=integration.id, project_id=test_project_id))
    await test_db_session.flush()
    resolved, revision = await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert resolved == config
    assert len(revision) == 64
    integration.enabled = False
    await test_db_session.flush()
    with pytest.raises(ApplicationError) as error:
        await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert error.value.non_retryable
