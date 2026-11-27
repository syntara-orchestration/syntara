"""Kafka credential requirements follow the effective transport on every operation."""

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.credentials.exceptions import CredentialValidationError
from syntara.credentials.lib.preseed import MTLS_CLIENT_IDENTITY_TYPE_NAME, preseed_credential_types
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.integrations.exceptions import IntegrationCredentialRequiredError
from syntara.integrations.models.integration import IntegrationCreate, IntegrationType, IntegrationUpdate
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.integrations.services.integration_service import IntegrationService


@pytest.mark.parametrize(
    ("protocol", "skip_tls", "message"),
    [
        ("PLAINTEXT", False, "Select SSL"),
        ("SASL_SSL", False, "Select SSL"),
        ("SSL", True, "Turn on TLS certificate verification"),
    ],
)
async def test_mtls_credential_checks_effective_settings_on_create_and_update(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
    protocol: str,
    *,
    skip_tls: bool,
    message: str,
) -> None:
    await preseed_credential_types(test_db_session)
    credential_type = (
        await test_db_session.exec(select(CredentialType).where(CredentialType.name == MTLS_CLIENT_IDENTITY_TYPE_NAME))
    ).one()
    credential = Credential(
        name="Client identity reference",
        credential_type_id=credential_type.id,
        project_id=test_project_id,
        created_by=test_user.id,
    )
    test_db_session.add(credential)
    await test_db_session.flush()

    service = IntegrationService(test_db_session, test_user)
    config = KafkaConfiguration(bootstrap_servers=["broker.example:9093"], security_protocol="SSL")
    incompatible = KafkaConfiguration(
        bootstrap_servers=config.bootstrap_servers,
        security_protocol=protocol,
        allow_plaintext=protocol == "PLAINTEXT",
        insecure_skip_tls_verify=skip_tls,
    )
    with patch.object(service, "_validate_configuration_ssrf", new_callable=AsyncMock) as address_check:
        saved = await service.create_integration(
            IntegrationCreate(
                name="Broker with client identity",
                integration_type=IntegrationType.KAFKA,
                configuration=config,
                management_credential_id=credential.id,
            )
        )
        assert saved.management_credential_id == credential.id
        address_check.reset_mock()
        with pytest.raises(CredentialValidationError, match=message):
            await service.create_integration(
                IntegrationCreate(
                    name="Incompatible broker",
                    integration_type=IntegrationType.KAFKA,
                    configuration=incompatible,
                    management_credential_id=credential.id,
                )
            )
        with pytest.raises(CredentialValidationError, match=message):
            await service.update_integration(saved.id, IntegrationUpdate(configuration=incompatible))
        address_check.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["SSL", "PLAINTEXT"])
async def test_create_without_credential_and_switch_to_sasl(
    test_db_session: AsyncSession, test_user: User, protocol: str
) -> None:
    """Optional-auth creates work; omitting a credential when enabling SASL fails."""
    service = IntegrationService(test_db_session, test_user)
    configuration = {
        "integration_type": "kafka",
        "bootstrap_servers": ["broker.example.com:9093"],
        "security_protocol": protocol,
        "allow_plaintext": protocol == "PLAINTEXT",
    }
    with patch("syntara.integrations.services.integration_service.validate_integration_configuration_no_ssrf"):
        created = await service.create_integration(
            IntegrationCreate(
                name=f"Kafka {protocol}", integration_type=IntegrationType.KAFKA, configuration=configuration
            )
        )
        assert created.management_credential_id is None
        with pytest.raises(IntegrationCredentialRequiredError):
            await service.update_integration(
                created.id, IntegrationUpdate(configuration={**configuration, "security_protocol": "SASL_SSL"})
            )
        unchanged = await service.get_integration(created.id)
        assert isinstance(unchanged.configuration, KafkaConfiguration)
        assert unchanged.configuration.security_protocol == protocol


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["SSL", "PLAINTEXT", "SASL_SSL"])
async def test_supplied_credential_must_be_kafka_for_every_transport(protocol: str) -> None:
    """Optional authentication does not make an unrelated credential valid."""
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    credential = MagicMock(spec=Credential)
    credential.enabled = True
    credential.secret_id = uuid4()
    credential.credential_type_id = uuid4()
    cred_type = MagicMock(spec=CredentialType)
    cred_type.name = "HTTP Bearer Token"
    cred_type.injectors = {}
    session = AsyncMock(spec=AsyncSession)
    session.get.side_effect = [credential, cred_type, credential, cred_type]
    secrets = AsyncMock()
    secrets.retrieve_secret.return_value = {}
    service = IntegrationService(session, MagicMock(spec=User), secrets)

    with pytest.raises(CredentialValidationError, match="not a Kafka credential"):
        await service._resolve_credential(uuid4(), security_protocol=protocol)
    secrets.retrieve_secret.assert_not_awaited()
