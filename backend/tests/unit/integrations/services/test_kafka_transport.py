"""Kafka credential requirements follow the effective transport on every operation."""

from unittest.mock import patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.exceptions import IntegrationCredentialRequiredError
from syntara.integrations.models.integration import IntegrationCreate, IntegrationType, IntegrationUpdate
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.integrations.services.integration_service import IntegrationService


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

    from syntara.credentials.exceptions import CredentialValidationError
    from syntara.credentials.models.credential import Credential
    from syntara.credentials.models.credential_type import CredentialType

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
