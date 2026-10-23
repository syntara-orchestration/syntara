"""Tests for Kafka credential rules and secret masking."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.core.lib.encryption import ENCRYPTED_SENTINEL, EncryptionError
from syntara.credentials.exceptions import CredentialDecryptionError, CredentialValidationError
from syntara.credentials.lib.kafka_connection import (
    resolve_connector_kafka_login,
    resolve_listener_kafka_login,
    resolve_supplied_kafka_login,
)
from syntara.credentials.lib.preseed import GA_CREDENTIAL_TYPES
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.credentials.services.credential_service import CredentialService


def _kafka_type() -> CredentialType:
    definition = next(item for item in GA_CREDENTIAL_TYPES if item["name"] == "Kafka")
    return CredentialType(
        id=uuid4(),
        name=definition["name"],
        description=definition["description"],
        inputs=definition["inputs"],
        injectors=definition["injectors"],
        managed=True,
    )


class TestKafkaCredentialRequirement:
    """SASL_SSL requires the credential. Other modes accept an omission."""

    @pytest.mark.parametrize("protocol", ["PLAINTEXT", "SSL"])
    def test_non_sasl_modes_accept_an_omitted_credential(self, protocol: str) -> None:
        assert (
            resolve_supplied_kafka_login(
                credential_id=None,
                decrypted_inputs=None,
                security_protocol=protocol,
            )
            is None
        )

    def test_sasl_ssl_requires_a_credential(self) -> None:
        with pytest.raises(CredentialValidationError, match="SASL_SSL requires a Kafka credential"):
            resolve_supplied_kafka_login(
                credential_id=None,
                decrypted_inputs=None,
                security_protocol="SASL_SSL",
            )

    def test_unsupported_protocol_is_rejected(self) -> None:
        with pytest.raises(CredentialValidationError, match="Unsupported Kafka security protocol"):
            resolve_supplied_kafka_login(
                credential_id=None,
                decrypted_inputs=None,
                security_protocol="SASL_PLAINTEXT",
            )


class TestSuppliedKafkaLogin:
    """Resolution uses only the credential the caller passed in."""

    def test_returns_the_supplied_login(self) -> None:
        credential_id = uuid4()
        resolved = resolve_supplied_kafka_login(
            credential_id=credential_id,
            decrypted_inputs={"username": "listener", "password": "listener-secret"},
            security_protocol="SASL_SSL",
        )

        assert resolved == {"kafka_username": "listener", "kafka_password": "listener-secret"}

    def test_preserves_password_whitespace(self) -> None:
        resolved = resolve_supplied_kafka_login(
            credential_id=uuid4(),
            decrypted_inputs={"username": "listener", "password": "  listener-secret  "},
            security_protocol="SASL_SSL",
        )

        assert resolved is not None
        assert resolved["kafka_password"] == "  listener-secret  "  # noqa: S105

    def test_rejects_whitespace_only_password(self) -> None:
        with pytest.raises(CredentialValidationError, match="username and password are required"):
            resolve_supplied_kafka_login(
                credential_id=uuid4(),
                decrypted_inputs={"username": "listener", "password": "   "},
                security_protocol="SASL_SSL",
            )

    def test_does_not_substitute_another_credential(self) -> None:
        management_inputs = {"username": "admin", "password": "admin-secret"}
        resolved = resolve_supplied_kafka_login(
            credential_id=uuid4(),
            decrypted_inputs={"username": "listener", "password": "listener-secret"},
            security_protocol="SASL_SSL",
        )

        assert resolved is not None
        assert resolved["kafka_username"] == "listener"
        assert management_inputs["password"] not in resolved.values()

    def test_blank_login_error_omits_the_password(self) -> None:
        with pytest.raises(CredentialValidationError, match="username and password are required") as exc_info:
            resolve_supplied_kafka_login(
                credential_id=uuid4(),
                decrypted_inputs={"username": "   ", "password": "super-secret-value"},
                security_protocol="SASL_SSL",
            )

        assert "super-secret-value" not in str(exc_info.value)

    def test_missing_inputs_do_not_fall_back(self) -> None:
        with pytest.raises(CredentialValidationError, match="inputs were not supplied"):
            resolve_supplied_kafka_login(
                credential_id=uuid4(),
                decrypted_inputs=None,
                security_protocol="SASL_SSL",
            )


class TestKafkaPasswordMasking:
    """GET responses mask the Kafka password and leave the username readable."""

    def test_password_is_masked_and_username_is_readable(self) -> None:
        kafka_type = _kafka_type()
        stored_value = "super-secret-value"
        credential = Credential(
            id=uuid4(),
            name="Kafka Cluster",
            credential_type_id=kafka_type.id,
            secret_id=uuid4(),
            enabled=True,
            project_id=uuid4(),
            created_by=uuid4(),
        )
        service = CredentialService(MagicMock(), MagicMock(), MagicMock())

        read = service._build_masked_response(
            credential,
            kafka_type,
            {"username": "avnadmin", "password": stored_value},
        )

        assert read.inputs["username"] == "avnadmin"
        assert read.inputs["password"] == ENCRYPTED_SENTINEL
        assert stored_value not in str(read.inputs)


def _stored_kafka_credential(username: str, stored_password: str) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Build a Kafka credential, its type, and a SecretService that returns the login."""
    credential = MagicMock()
    credential.id = uuid4()
    credential.name = "Kafka login"
    credential.enabled = True
    credential.secret_id = uuid4()
    credential.credential_type_id = uuid4()
    cred_type = MagicMock()
    cred_type.name = "Kafka"
    secret_service = MagicMock()
    secret_service.retrieve_secret = AsyncMock(return_value={"username": username, "password": stored_password})
    return credential, cred_type, secret_service


def _session_for(credentials: dict[object, MagicMock], types: dict[object, MagicMock]) -> AsyncMock:
    session = AsyncMock()

    async def get(model: object, obj_id: object) -> MagicMock | None:
        if model is Credential:
            return credentials.get(obj_id)
        if model is CredentialType:
            return types.get(obj_id)
        return None

    session.get = AsyncMock(side_effect=get)
    return session


class TestKafkaCredentialResolution:
    """Connector and listener resolution load only the id the caller supplied."""

    @pytest.mark.asyncio
    async def test_connector_decrypts_the_management_credential(self) -> None:
        credential, cred_type, secret_service = _stored_kafka_credential("admin", "  admin-secret  ")
        session = _session_for({credential.id: credential}, {credential.credential_type_id: cred_type})

        resolved = await resolve_connector_kafka_login(
            session,
            secret_service,
            management_credential_id=credential.id,
            security_protocol="SASL_SSL",
        )

        assert resolved == {"kafka_username": "admin", "kafka_password": "  admin-secret  "}
        secret_service.retrieve_secret.assert_awaited_once_with(credential.secret_id)

    @pytest.mark.asyncio
    async def test_listener_uses_the_step_credential_only(self) -> None:
        management, management_type, _management_secrets = _stored_kafka_credential("admin", "admin-secret")
        listener, listener_type, listener_secrets = _stored_kafka_credential("listener", "  listener-secret  ")
        session = _session_for(
            {management.id: management, listener.id: listener},
            {management.credential_type_id: management_type, listener.credential_type_id: listener_type},
        )

        resolved = await resolve_listener_kafka_login(
            session,
            listener_secrets,
            runtime_credential_id=listener.id,
            security_protocol="SASL_SSL",
        )

        assert resolved is not None
        assert resolved["kafka_username"] == "listener"
        assert resolved["kafka_password"] == "  listener-secret  "  # noqa: S105
        assert "admin-secret" not in resolved.values()
        listener_secrets.retrieve_secret.assert_awaited_once_with(listener.secret_id)
        requested_ids = [call.args[1] for call in session.get.await_args_list]
        assert management.id not in requested_ids

    @pytest.mark.asyncio
    async def test_missing_runtime_credential_does_not_read_another_secret(self) -> None:
        management, management_type, secret_service = _stored_kafka_credential("admin", "admin-secret")
        session = _session_for({management.id: management}, {management.credential_type_id: management_type})

        with pytest.raises(CredentialValidationError, match="SASL_SSL requires a Kafka credential"):
            await resolve_listener_kafka_login(
                session,
                secret_service,
                runtime_credential_id=None,
                security_protocol="SASL_SSL",
            )

        secret_service.retrieve_secret.assert_not_awaited()
        session.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_a_non_kafka_credential(self) -> None:
        credential, cred_type, secret_service = _stored_kafka_credential("admin", "admin-secret")
        cred_type.name = "HTTP Basic Auth"
        session = _session_for({credential.id: credential}, {credential.credential_type_id: cred_type})

        with pytest.raises(CredentialValidationError, match="not a Kafka credential"):
            await resolve_connector_kafka_login(
                session,
                secret_service,
                management_credential_id=credential.id,
                security_protocol="SASL_SSL",
            )

        secret_service.retrieve_secret.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_decryption_failure_omits_the_password(self) -> None:
        credential, cred_type, secret_service = _stored_kafka_credential("admin", "admin-secret")
        secret_service.retrieve_secret = AsyncMock(side_effect=EncryptionError("admin-secret"))
        session = _session_for({credential.id: credential}, {credential.credential_type_id: cred_type})

        with pytest.raises(CredentialDecryptionError, match="could not be decrypted") as exc_info:
            await resolve_connector_kafka_login(
                session,
                secret_service,
                management_credential_id=credential.id,
                security_protocol="SASL_SSL",
            )

        assert "admin-secret" not in str(exc_info.value)


class TestConnectorValidationCallSite:
    """Saved connector validation resolves the management credential through SecretService."""

    @pytest.mark.asyncio
    async def test_resolve_credential_uses_the_kafka_management_login(self) -> None:
        from syntara.integrations.services.integration_service import IntegrationService

        credential, cred_type, secret_service = _stored_kafka_credential("admin", "  admin-secret  ")
        session = _session_for({credential.id: credential}, {credential.credential_type_id: cred_type})
        service = IntegrationService(session, MagicMock(), secret_service)

        resolved = await service._resolve_credential(credential.id)

        assert resolved["kafka_username"] == "admin"
        assert resolved["kafka_password"] == "  admin-secret  "  # noqa: S105
        secret_service.retrieve_secret.assert_awaited_once_with(credential.secret_id)
