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
