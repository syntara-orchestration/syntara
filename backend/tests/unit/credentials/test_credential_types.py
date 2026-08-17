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

    def test_six_ga_types_defined(self) -> None:
        assert len(GA_CREDENTIAL_TYPES) == 6

    @pytest.mark.parametrize(
        "name",
        [
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

    def test_all_have_injector_sections(self) -> None:
        for type_def in GA_CREDENTIAL_TYPES:
            injectors = type_def["injectors"]
            assert "extra_vars" in injectors
            assert "env" in injectors
            assert "file" in injectors
