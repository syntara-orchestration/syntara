"""Runtime binding checks and production revision generation without broker I/O."""

from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.lib.encryption import EncryptionError
from syntara.core.services.secret_service import SecretService
from syntara.core.storage_exceptions import StorageBackendNotFoundError
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import connection_provider as provider_module
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.integrations.models.integration import Integration, IntegrationScope, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from tests.unit.eventstreams.test_connection_revision import NOW
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription


@dataclass
class ConnectionContext:
    """Runtime resources and isolated database/secret ports."""

    snapshot: SubscriptionSnapshot
    integration: Integration
    credential: Credential
    credential_type: CredentialType
    session: MagicMock
    secrets: MagicMock
    provider: EventConnectionProvider


def connection_context() -> ConnectionContext:
    """Supply real resource objects and only fake database/secret I/O."""
    subscription = _subscription()
    snapshot = SubscriptionSnapshot.from_models(subscription, _source(subscription))
    integration = Integration(
        id=snapshot.integration_id,
        name="Kafka",
        integration_type=IntegrationType.KAFKA,
        configuration=KafkaConfiguration(bootstrap_servers=["broker:9092"]),
        created_by=UUID(int=1),
        updated_at=NOW,
    )
    credential_type = CredentialType(
        name="Kafka",
        updated_at=NOW,
        injectors={"extra_vars": {"kafka_username": "{{username}}", "kafka_password": "{{password}}"}},
    )
    credential = Credential(
        id=snapshot.runtime_credential_id,
        name="Runtime",
        project_id=snapshot.project_id,
        credential_type_id=credential_type.id,
        secret_id=UUID(int=20),
        created_by=UUID(int=1),
        updated_at=NOW,
    )
    session = MagicMock(spec=AsyncSession)
    rows = {Integration: integration, Credential: credential, CredentialType: credential_type}
    session.get = AsyncMock(side_effect=lambda model, _key: rows.get(model))
    session.exec = AsyncMock(return_value=MagicMock())
    session.exec.return_value.one_or_none.return_value = NOW
    secrets = MagicMock(spec=SecretService)
    secrets.retrieve_secret = AsyncMock(return_value={"username": "PRIVATE_USER", "password": "PRIVATE_PASSWORD"})
    return ConnectionContext(
        snapshot,
        integration,
        credential,
        credential_type,
        session,
        secrets,
        EventConnectionProvider(session, secret_service=secrets),
    )


async def test_producer_uses_identifiers_and_storage_change_timestamp() -> None:
    context = connection_context()
    first = await context.provider.resolve_revision(context.snapshot)
    context.secrets.retrieve_secret.return_value = {
        "username": "OTHER_PRIVATE_USER",
        "password": "OTHER_PRIVATE_PASSWORD",
    }
    assert (await context.provider.resolve_revision(context.snapshot)).digest == first.digest
    context.session.exec.return_value.one_or_none.return_value = NOW + timedelta(microseconds=1)
    assert (await context.provider.resolve_revision(context.snapshot)).digest != first.digest
    assert "PRIVATE" not in first.model_dump_json()
    # Only the storage timestamp is selected by the revision producer.
    query = str(context.session.exec.call_args.args[0])
    assert "encrypted_secrets.updated_at" in query
    assert "encrypted_data" not in query


@pytest.mark.parametrize("resource", ["integration", "credential", "credential_type"])
async def test_producer_tracks_configuration_and_credential_edits(resource: str) -> None:
    context = connection_context()
    before = await context.provider.resolve_revision(context.snapshot)
    getattr(context, resource).updated_at += timedelta(microseconds=1)
    assert (await context.provider.resolve_revision(context.snapshot)).digest != before.digest


@pytest.mark.parametrize("resource", ["integration", "credential"])
async def test_disabled_runtime_resources_block(resource: str) -> None:
    context = connection_context()
    getattr(context, resource).enabled = False
    with pytest.raises(SafeValueError, match="unavailable"):
        await context.provider.resolve_revision(context.snapshot)
    context.secrets.retrieve_secret.assert_not_awaited()


async def test_credential_must_belong_to_workflow_project() -> None:
    context = connection_context()
    context.credential.project_id = UUID(int=99)
    with pytest.raises(SafeValueError, match="unavailable"):
        await context.provider.resolve_revision(context.snapshot)


async def test_project_scoped_integration_requires_assignment() -> None:
    context = connection_context()
    context.integration.scope = IntegrationScope.PROJECT
    context.session.exec.return_value.first.return_value = None
    with pytest.raises(SafeValueError, match="outside"):
        await context.provider.resolve_revision(context.snapshot)
    context.session.exec.return_value.first.return_value = UUID(int=5)
    assert await context.provider.resolve_revision(context.snapshot)


async def test_missing_encrypted_storage_blocks_revision() -> None:
    context = connection_context()
    context.session.exec.return_value.one_or_none.return_value = None
    with pytest.raises(SafeValueError, match="secret is unavailable"):
        await context.provider.resolve_revision(context.snapshot)


@pytest.mark.parametrize(
    "failure",
    [
        EncryptionError("PRIVATE"),
        StorageBackendNotFoundError("PRIVATE"),
        KeyError("PRIVATE"),
        TypeError("PRIVATE"),
        ValueError("PRIVATE"),
        AttributeError("PRIVATE"),
    ],
)
async def test_resolution_failure_is_logged_without_secret_contents(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    context = connection_context()
    context.secrets.retrieve_secret.side_effect = failure
    log = MagicMock()
    monkeypatch.setattr(provider_module, "logger", log)
    with pytest.raises(SafeValueError, match="cannot be resolved") as error:
        await context.provider.resolve_revision(context.snapshot)
    assert "PRIVATE" not in str(error.value)
    log.warning.assert_called_once_with(
        "Event runtime credential resolution failed",
        credential_id=str(context.credential.id),
        error_type=type(failure).__name__,
    )
    log.exception.assert_not_called()


@pytest.mark.parametrize(
    "inputs",
    [
        {},
        {"username": "PRIVATE_USER"},
        {"password": "PRIVATE_PASSWORD"},
        {"username": "", "password": "PRIVATE_PASSWORD"},
        {"username": "PRIVATE_USER", "password": ""},
        {"username": " \t", "password": "PRIVATE_PASSWORD"},
        {"username": "PRIVATE_USER", "password": " \t"},
        {"username": None, "password": "PRIVATE_PASSWORD"},
        {"username": "PRIVATE_USER", "password": None},
    ],
)
async def test_unusable_authentication_cannot_produce_revision(
    monkeypatch: pytest.MonkeyPatch,
    inputs: dict[str, object],
) -> None:
    context = connection_context()
    context.secrets.retrieve_secret.return_value = inputs
    log = MagicMock()
    monkeypatch.setattr(provider_module, "logger", log)
    with pytest.raises(SafeValueError, match="cannot be resolved") as error:
        await context.provider.resolve_revision(context.snapshot)
    assert "PRIVATE" not in str(error.value)
    log.warning.assert_called_once_with(
        "Event runtime credential resolution failed",
        credential_id=str(context.credential.id),
        error_type="SafeValueError",
    )


async def test_missing_authentication_injectors_cannot_produce_revision() -> None:
    context = connection_context()
    context.credential_type.injectors = {}
    with pytest.raises(SafeValueError, match="cannot be resolved"):
        await context.provider.resolve_revision(context.snapshot)
