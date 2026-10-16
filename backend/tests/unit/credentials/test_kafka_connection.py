"""Tests for Kafka credential rules and secret masking."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from syntara.core.lib.encryption import ENCRYPTED_SENTINEL
from syntara.credentials.exceptions import CredentialValidationError
from syntara.credentials.lib.kafka_connection import (
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
