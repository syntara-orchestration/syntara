"""Check Publish references against the same database scope used by other actions."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.exceptions import ApplicationError

from syntara.core.models import User
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.lib.preseed import MTLS_CLIENT_IDENTITY_TYPE_NAME, preseed_credential_types
from syntara.credentials.models.credential import Credential, CredentialCreate, CredentialUpdate
from syntara.credentials.models.credential_type import CredentialType
from syntara.credentials.services.credential_service import CredentialService
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities.kafka_publish_connection import current_publish_resources
from syntara.workflows.workflow_engine.models.kafka_publish import KafkaPublishParameters
from tests.fixtures.tls import generate_self_signed_cert


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["SASL_SSL", "SSL", "PLAINTEXT"])
async def test_project_scope_and_disabling_are_checked_without_management_fallback(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID, protocol: str
) -> None:
    config = KafkaConfiguration(
        bootstrap_servers=["broker.example.com:9092"],
        security_protocol=protocol,
        allow_plaintext=protocol == "PLAINTEXT",
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
    # Reuse the managed type when the shared database has already been seeded.
    credential_type = (await test_db_session.exec(select(CredentialType).where(CredentialType.name == "Kafka"))).first()
    if credential_type is None:
        credential_type = CredentialType(name="Kafka", inputs={}, injectors={})
        test_db_session.add(credential_type)
        await test_db_session.flush()
    credential = Credential(
        name=f"runtime-{uuid4().hex}",
        credential_type_id=credential_type.id,
        project_id=test_project_id,
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(credential)
    await test_db_session.flush()
    parameters = KafkaPublishParameters(
        integration_id=str(integration.id), credential_id=str(credential.id), topic="outcomes", payload=None
    )
    with pytest.raises(ApplicationError) as error:
        await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert error.value.non_retryable
    test_db_session.add(IntegrationProjectAssignment(integration_id=integration.id, project_id=test_project_id))
    await test_db_session.flush()
    if protocol == "SASL_SSL":
        # An existing, enabled credential still needs SASL inputs in this mode.
        with pytest.raises(ApplicationError) as error:
            await current_publish_resources(test_db_session, parameters, str(test_project_id))
        assert error.value.non_retryable
        return
    resolved, revision, type_name = await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert resolved == config
    assert len(revision) == 64
    assert type_name == "Kafka"
    integration.enabled = False
    await test_db_session.flush()
    with pytest.raises(ApplicationError) as error:
        await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert error.value.non_retryable

    integration.enabled = True
    credential.enabled = False
    await test_db_session.flush()
    with pytest.raises(ApplicationError) as error:
        await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert error.value.non_retryable


async def test_publish_identity_revision_tracks_rotation_disable_and_delete(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID, tmp_path: Path
) -> None:
    await preseed_credential_types(test_db_session)
    identity_type = (
        await test_db_session.exec(select(CredentialType).where(CredentialType.name == MTLS_CLIENT_IDENTITY_TYPE_NAME))
    ).one()
    service = CredentialService(test_db_session, test_user, create_secret_service(test_db_session))
    certificate, private_key = generate_self_signed_cert(tmp_path, "publish", "original")
    stored = {"client_certificate": certificate.read_text(), "client_private_key": private_key.read_text()}
    management = await service.create_credential(
        CredentialCreate(
            name="Management identity", credential_type_id=identity_type.id, project_id=test_project_id, inputs=stored
        )
    )
    runtime = await service.create_credential(
        CredentialCreate(
            name="Runtime identity", credential_type_id=identity_type.id, project_id=test_project_id, inputs=stored
        )
    )
    integration = Integration(
        name="Broker with management identity",
        integration_type=IntegrationType.KAFKA,
        configuration=KafkaConfiguration(bootstrap_servers=["broker.example:9093"], security_protocol="SSL"),
        management_credential_id=management.id,
        scope=IntegrationScope.GLOBAL,
        created_by=test_user.id,
    )
    test_db_session.add(integration)
    await test_db_session.flush()
    parameters = KafkaPublishParameters(
        integration_id=str(integration.id), credential_id=str(runtime.id), topic="outcomes", payload=None
    )
    _, before, credential_type_name = await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert credential_type_name == MTLS_CLIENT_IDENTITY_TYPE_NAME

    certificate, private_key = generate_self_signed_cert(tmp_path, "rotated publish", "rotated")
    await service.update_credential(
        runtime.id,
        CredentialUpdate(
            inputs={"client_certificate": certificate.read_text(), "client_private_key": private_key.read_text()}
        ),
    )
    _, after, _ = await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert before != after

    await service.update_credential(runtime.id, CredentialUpdate(enabled=False))
    with pytest.raises(ApplicationError) as disabled:
        await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert disabled.value.type == "kafka_invalid_reference"

    await service.delete_credential(runtime.id)
    with pytest.raises(ApplicationError) as deleted:
        await current_publish_resources(test_db_session, parameters, str(test_project_id))
    assert deleted.value.type == "kafka_invalid_reference"
    assert (await service.get_credential(management.id)).enabled
