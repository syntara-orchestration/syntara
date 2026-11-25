"""Tests for CredentialType model and GA credential type definitions."""

import pytest

from syntara.credentials.lib.preseed import GA_CREDENTIAL_TYPES
from syntara.credentials.models.credential_type import CredentialType, CredentialTypeRead


class TestCredentialTypeModel:
    """Tests for CredentialType model validation."""

    def test_create_credential_type(self) -> None:
        ct = CredentialType(
            name="Test Type",
            inputs={"fields": [], "required": []},
            injectors={"extra_vars": {}},
            managed=False,
        )
        assert ct.name == "Test Type"
        assert ct.managed is False

    def test_read_schema_from_model(self) -> None:
        ct = CredentialType(
            name="Test Type",
            description="A test",
            inputs={"fields": [{"id": "token", "type": "string", "secret": True, "label": "Token"}]},
            injectors={"extra_vars": {"token": "{{token}}"}},
            managed=True,
        )
        read = CredentialTypeRead.model_validate(ct)
        assert read.name == "Test Type"
        assert read.managed is True
        assert len(read.inputs["fields"]) == 1


class TestGACredentialTypes:
    """Tests for GA managed credential type definitions."""

    def test_ga_types_defined(self) -> None:
        assert len(GA_CREDENTIAL_TYPES) == 8

    @pytest.mark.parametrize(
        "name",
        [
            "Kafka",
            "mTLS Client Identity",
            "HTTP Bearer Token",
            "HTTP Basic Auth",
            "Ansible Automation Platform",
            "LLM Provider",
            "SSH Key",
            "Secret URL",
        ],
    )
    def test_ga_type_exists(self, name: str) -> None:
        names = [t["name"] for t in GA_CREDENTIAL_TYPES]
        assert name in names

    def test_all_have_required_fields(self) -> None:
        for type_def in GA_CREDENTIAL_TYPES:
            assert "name" in type_def
            assert "description" in type_def
            assert "inputs" in type_def
            assert "injectors" in type_def
            assert "fields" in type_def["inputs"]
            assert "required" in type_def["inputs"]

    def test_kafka_connection_is_username_and_password_only(self) -> None:
        kafka = next(item for item in GA_CREDENTIAL_TYPES if item["name"] == "Kafka")
        fields = kafka["inputs"]["fields"]

        assert [field["id"] for field in fields] == ["username", "password"]
        assert kafka["inputs"]["required"] == []
        assert kafka["inputs"]["required_together"] == [["username", "password"]]
        assert fields[0]["secret"] is False
        assert fields[1]["secret"] is True
        assert kafka["injectors"]["extra_vars"]["auth_type"] == "kafka_connection"
        assert "SASL_SSL requires a username and password" in kafka["description"]

    def test_mtls_identity_schema_and_injectors(self) -> None:
        identity = next(item for item in GA_CREDENTIAL_TYPES if item["name"] == "mTLS Client Identity")
        inputs = identity["inputs"]
        certificate, private_key, passphrase = inputs["fields"]

        assert identity["description"] == "Lets a service prove its identity to an external system that requires mTLS."
        assert [field["id"] for field in inputs["fields"]] == [
            "client_certificate",
            "client_private_key",
            "client_key_passphrase",
        ]
        assert inputs["required"] == ["client_certificate", "client_private_key"]
        assert not inputs.get("required_together")
        assert certificate["multiline"] is True
        assert certificate["secret"] is False
        assert certificate["default"] == "-----BEGIN CERTIFICATE-----\n\n-----END CERTIFICATE-----"
        assert private_key["multiline"] is True
        assert private_key["secret"] is True
        assert passphrase["secret"] is True
        assert not passphrase.get("multiline")
        assert passphrase["min_length"] == 4
        assert identity["injectors"]["extra_vars"] == {
            "mtls_client_certificate": "{{client_certificate}}",
            "mtls_client_private_key": "{{client_private_key}}",
            "mtls_client_key_passphrase": "{{client_key_passphrase}}",
        }

    def test_all_have_injector_sections(self) -> None:
        for type_def in GA_CREDENTIAL_TYPES:
            injectors = type_def["injectors"]
            assert "extra_vars" in injectors
            assert "env" in injectors
            assert "file" in injectors
