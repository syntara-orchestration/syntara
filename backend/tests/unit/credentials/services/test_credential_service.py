"""Tests for CredentialService — CRUD operations via SecretService."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from contextlib import AbstractContextManager
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syntara.authz.exceptions import BuiltinProtectionError
from syntara.core.lib.encryption import ENCRYPTED_SENTINEL
from syntara.credentials.exceptions import (
    CredentialNameConflictError,
    CredentialNotFoundError,
    CredentialValidationError,
)
from syntara.credentials.models.credential import Credential, CredentialCreate, CredentialRead, CredentialUpdate
from syntara.credentials.models.credential_type import CredentialType
from syntara.credentials.services.credential_service import (
    CredentialService,
    _get_secret_field_ids,
    _mask_all_secrets,
    _validate_field_constraints,
    _validate_field_value,
    _validate_inputs,
    _validate_ssh_private_key,
)

BEARER_TYPE_INPUTS = {
    "fields": [
        {"id": "token", "label": "Token", "type": "string", "secret": True},
    ],
    "required": ["token"],
}

BASIC_AUTH_TYPE_INPUTS = {
    "fields": [
        {"id": "username", "label": "Username", "type": "string", "secret": False},
        {"id": "password", "label": "Password", "type": "string", "secret": True},
    ],
    "required": ["username", "password"],
}

BOOLEAN_TYPE_INPUTS = {
    "fields": [
        {"id": "verify_ssl", "label": "Verify SSL", "type": "boolean", "secret": False},
    ],
    "required": [],
}

SSH_TYPE_INPUTS = {
    "fields": [
        {"id": "username", "label": "Username", "type": "string", "secret": False},
        {"id": "ssh_private_key", "label": "Key", "type": "string", "secret": True, "multiline": True},
    ],
    "required": ["username", "ssh_private_key"],
}

HOST_TYPE_INPUTS = {
    "fields": [
        {"id": "host", "label": "Host", "type": "string", "secret": False},
        {"id": "token", "label": "Token", "type": "string", "secret": True},
    ],
    "required": ["host"],
}

AAP_TYPE_INPUTS = {
    "fields": [
        {"id": "username", "label": "Username", "type": "string", "secret": False},
        {"id": "password", "label": "Password", "type": "string", "secret": True},
        {"id": "oauth_token", "label": "OAuth Token", "type": "string", "secret": True},
    ],
    "required": [],
    "mutually_exclusive": [
        ["oauth_token"],
        ["username", "password"],
    ],
    "required_one_of": [
        ["oauth_token"],
        ["username", "password"],
    ],
    "required_together": [
        ["username", "password"],
    ],
}


@pytest.fixture
def mock_secret_service() -> MagicMock:
    """Create a mock SecretService."""
    service = MagicMock()
    service.create_secret = AsyncMock(return_value=uuid4())
    service.retrieve_secret = AsyncMock(return_value={})
    service.update_secret = AsyncMock()
    service.delete_secret = AsyncMock()
    return service


@pytest.fixture(autouse=True)
def _mock_workflow_counts() -> Generator[None, None, None]:
    """Mock get_workflow_counts to avoid session.exec conflicts in unit tests."""
    with patch.object(CredentialService, "get_workflow_counts", new_callable=AsyncMock, return_value={}):
        yield


@pytest.fixture(autouse=True)
def _mock_integration_counts() -> Generator[None, None, None]:
    """Mock get_integration_counts to avoid session.exec conflicts in unit tests."""
    with patch.object(CredentialService, "get_integration_counts", new_callable=AsyncMock, return_value={}):
        yield


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock AsyncSession."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.exec = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> MagicMock:
    """Create a mock User."""
    user = MagicMock()
    user.id = uuid4()
    return user


@pytest.fixture
def bearer_type() -> CredentialType:
    """Create a bearer token credential type."""
    return CredentialType(
        id=uuid4(),
        name="HTTP Bearer Token",
        inputs=BEARER_TYPE_INPUTS,
        injectors={"extra_vars": {"bearer_token": "{{token}}"}},
        managed=True,
    )


@pytest.fixture
def basic_auth_type() -> CredentialType:
    """Create a basic auth credential type."""
    return CredentialType(
        id=uuid4(),
        name="HTTP Basic Auth",
        inputs=BASIC_AUTH_TYPE_INPUTS,
        injectors={"extra_vars": {"basic_username": "{{username}}", "basic_password": "{{password}}"}},
        managed=True,
    )


@pytest.fixture
def aap_type() -> CredentialType:
    """Create an AAP credential type with mutually exclusive auth groups."""
    return CredentialType(
        id=uuid4(),
        name="Ansible Automation Platform",
        inputs=AAP_TYPE_INPUTS,
        injectors={"extra_vars": {}},
        managed=True,
    )


class TestGetSecretFieldIds:
    """Tests for _get_secret_field_ids helper."""

    def test_extracts_secret_fields(self) -> None:
        result = _get_secret_field_ids(BASIC_AUTH_TYPE_INPUTS)
        assert result == {"password"}

    def test_all_secret(self) -> None:
        result = _get_secret_field_ids(BEARER_TYPE_INPUTS)
        assert result == {"token"}

    def test_empty_fields(self) -> None:
        result = _get_secret_field_ids({"fields": []})
        assert result == set()

    def test_no_fields_key(self) -> None:
        result = _get_secret_field_ids({})
        assert result == set()


class TestMaskAllSecrets:
    """Tests for _mask_all_secrets helper (list responses)."""

    def test_masks_all_fields(self) -> None:
        result = _mask_all_secrets(BASIC_AUTH_TYPE_INPUTS)
        assert result == {"username": ENCRYPTED_SENTINEL, "password": ENCRYPTED_SENTINEL}

    def test_single_field(self) -> None:
        result = _mask_all_secrets(BEARER_TYPE_INPUTS)
        assert result == {"token": ENCRYPTED_SENTINEL}

    def test_empty_type(self) -> None:
        result = _mask_all_secrets({})
        assert result == {}


class TestCreateCredential:
    """Tests for CredentialService.create_credential."""

    @pytest.mark.asyncio
    async def test_creates_with_inputs(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        bearer_type: CredentialType,
    ) -> None:
        mock_session.get.side_effect = [None, bearer_type]
        project_id = uuid4()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_result.first.side_effect = [project_id, None]
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)

        data = CredentialCreate(
            name="My Token",
            credential_type_id=bearer_type.id,
            inputs={"token": "sk-abc-123"},
            project_id=project_id,
        )
        result = await service.create_credential(data)

        mock_secret_service.create_secret.assert_awaited_once_with({"token": "sk-abc-123"})
        assert result.name == "My Token"
        assert result.inputs == {"token": ENCRYPTED_SENTINEL}

    @pytest.mark.asyncio
    async def test_creates_without_inputs_when_no_required(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        optional_type = CredentialType(
            id=uuid4(),
            name="Optional Fields Only",
            inputs={"fields": [{"id": "note", "type": "string", "secret": False, "label": "Note"}], "required": []},
            injectors={},
            managed=False,
        )
        mock_session.get.side_effect = [None, optional_type]
        project_id = uuid4()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_result.first.side_effect = [project_id, None]
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)

        data = CredentialCreate(
            name="Empty Cred",
            credential_type_id=optional_type.id,
            project_id=project_id,
        )
        result = await service.create_credential(data)

        mock_secret_service.create_secret.assert_not_awaited()
        assert result.name == "Empty Cred"

    @pytest.mark.asyncio
    async def test_name_conflict_raises(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        bearer_type: CredentialType,
    ) -> None:
        mock_session.get.side_effect = [None, bearer_type]
        existing_cred = MagicMock()
        project_id = uuid4()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_result.first.side_effect = [project_id, existing_cred]
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)

        data = CredentialCreate(
            name="Duplicate",
            credential_type_id=bearer_type.id,
            inputs={"token": "abc"},
            project_id=project_id,
        )
        with pytest.raises(CredentialNameConflictError):
            await service.create_credential(data)

    @pytest.mark.asyncio
    async def test_raises_when_project_is_builtin(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        builtin_project = MagicMock()
        builtin_project.is_builtin = True
        builtin_project.name = "Default"
        mock_session.get.return_value = builtin_project
        mock_result = MagicMock()
        mock_result.first.return_value = uuid4()
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        data = CredentialCreate(
            name="Blocked",
            credential_type_id=uuid4(),
            inputs={"token": "x"},
            project_id=uuid4(),
        )
        with pytest.raises(BuiltinProtectionError):
            await service.create_credential(data)


class TestGetCredential:
    """Tests for CredentialService.get_credential."""

    @pytest.mark.asyncio
    async def test_returns_masked_response(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        basic_auth_type: CredentialType,
    ) -> None:
        secret_id = uuid4()
        credential = Credential(
            id=uuid4(),
            name="My Cred",
            credential_type_id=basic_auth_type.id,
            secret_id=secret_id,
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )
        credential.credential_type = basic_auth_type

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result
        mock_session.get.return_value = basic_auth_type

        mock_secret_service.retrieve_secret.return_value = {
            "username": "admin",
            "password": "secret123",
        }

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        result = await service.get_credential(credential.id)

        mock_secret_service.retrieve_secret.assert_awaited_once_with(secret_id)
        assert result.inputs["username"] == "admin"
        assert result.inputs["password"] == ENCRYPTED_SENTINEL

    @pytest.mark.asyncio
    async def test_not_found_raises(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        with pytest.raises(CredentialNotFoundError):
            await service.get_credential(uuid4())


class TestUpdateCredential:
    """Tests for CredentialService.update_credential."""

    @pytest.mark.asyncio
    async def test_encrypted_sentinel_preserves_existing(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        basic_auth_type: CredentialType,
    ) -> None:
        secret_id = uuid4()
        credential = Credential(
            id=uuid4(),
            name="My Cred",
            credential_type_id=basic_auth_type.id,
            secret_id=secret_id,
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result
        mock_session.get.side_effect = [None, basic_auth_type]

        mock_secret_service.retrieve_secret.return_value = {
            "username": "admin",
            "password": "old-password",
        }

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        patch = CredentialUpdate(inputs={"username": "new-admin", "password": ENCRYPTED_SENTINEL})
        await service.update_credential(credential.id, patch)

        # Verify update was called with merged inputs (password preserved)
        call_args = mock_secret_service.update_secret.call_args
        updated_data = call_args[0][1]
        assert updated_data["username"] == "new-admin"
        assert updated_data["password"] == "old-password"  # noqa: S105

    @pytest.mark.asyncio
    async def test_patch_merged_state_rejects_conflicting_groups(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        aap_type: CredentialType,
    ) -> None:
        """PATCH that results in both auth groups populated is rejected before storing."""
        credential = Credential(
            id=uuid4(),
            name="AAP Cred",
            credential_type_id=aap_type.id,
            secret_id=uuid4(),
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result
        mock_session.get.side_effect = [None, aap_type]

        mock_secret_service.retrieve_secret.return_value = {
            "oauth_token": "existing-token",
        }

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        patch_data = CredentialUpdate(inputs={"username": "admin", "password": "secret"})

        with pytest.raises(CredentialValidationError, match="mutually exclusive"):
            await service.update_credential(credential.id, patch_data)

        mock_secret_service.update_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_legacy_credential_fails_on_any_patch_with_inputs(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        aap_type: CredentialType,
    ) -> None:
        """Legacy credential with both auth groups fails on PATCH even when not touching conflicting fields."""
        credential = Credential(
            id=uuid4(),
            name="Legacy AAP Cred",
            credential_type_id=aap_type.id,
            secret_id=uuid4(),
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result
        mock_session.get.side_effect = [None, aap_type]

        mock_secret_service.retrieve_secret.return_value = {
            "oauth_token": "tok",
            "username": "admin",
            "password": "secret",
        }

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        patch_data = CredentialUpdate(inputs={})

        with pytest.raises(CredentialValidationError, match="mutually exclusive"):
            await service.update_credential(credential.id, patch_data)

        mock_secret_service.update_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_project_is_builtin(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        credential = Credential(
            id=uuid4(),
            name="Builtin Cred",
            credential_type_id=uuid4(),
            secret_id=uuid4(),
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )
        builtin_project = MagicMock()
        builtin_project.is_builtin = True
        builtin_project.name = "Default"
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result
        mock_session.get.return_value = builtin_project

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        patch_data = CredentialUpdate()
        with pytest.raises(BuiltinProtectionError):
            await service.update_credential(credential.id, patch_data)

        mock_secret_service.update_secret.assert_not_called()


class TestDeleteCredential:
    """Tests for CredentialService.delete_credential."""

    @pytest.mark.asyncio
    async def test_hard_deletes_and_removes_secret(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        secret_id = uuid4()
        credential = Credential(
            id=uuid4(),
            name="To Delete",
            credential_type_id=uuid4(),
            secret_id=secret_id,
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        await service.delete_credential(credential.id)

        mock_secret_service.delete_secret.assert_awaited_once_with(secret_id)
        mock_session.delete.assert_awaited_once_with(credential)

    @pytest.mark.asyncio
    async def test_deletes_credential_without_secret(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        credential = Credential(
            id=uuid4(),
            name="No Secret",
            credential_type_id=uuid4(),
            secret_id=None,
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        await service.delete_credential(credential.id)

        mock_secret_service.delete_secret.assert_not_called()
        mock_session.delete.assert_awaited_once_with(credential)

    @pytest.mark.asyncio
    async def test_logs_warning_when_workflows_reference_credential(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        credential = Credential(
            id=uuid4(),
            name="Referenced Cred",
            credential_type_id=uuid4(),
            secret_id=uuid4(),
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)

        with (
            patch.object(service, "get_workflow_counts", new_callable=AsyncMock, return_value={credential.id: 3}),
            patch("syntara.credentials.services.credential_service.logger") as mock_logger,
        ):
            await service.delete_credential(credential.id)

            mock_logger.warning.assert_called_once()
            assert "still referenced by workflows" in mock_logger.warning.call_args[0][0]

        mock_session.delete.assert_awaited_once_with(credential)

    @pytest.mark.asyncio
    async def test_raises_when_project_is_builtin(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        credential = Credential(
            id=uuid4(),
            name="Builtin Cred",
            credential_type_id=uuid4(),
            secret_id=uuid4(),
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )
        builtin_project = MagicMock()
        builtin_project.is_builtin = True
        builtin_project.name = "Default"
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result
        mock_session.get.return_value = builtin_project

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        with pytest.raises(BuiltinProtectionError):
            await service.delete_credential(credential.id)

        mock_secret_service.delete_secret.assert_not_called()
        mock_session.delete.assert_not_awaited()


_real_get_integration_counts = CredentialService.get_integration_counts


class TestGetIntegrationCounts:
    """Tests for CredentialService.get_integration_counts."""

    @pytest.mark.asyncio
    async def test_empty_credential_ids_returns_empty(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        service = CredentialService(mock_session, mock_user, mock_secret_service)
        result = await _real_get_integration_counts(service, [])
        assert result == {}
        mock_session.exec.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_counts_for_matching_credentials(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        cred_id_1 = uuid4()
        cred_id_2 = uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [(cred_id_1, 3), (cred_id_2, 1)]
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        result = await _real_get_integration_counts(service, [cred_id_1, cred_id_2])

        assert result == {cred_id_1: 3, cred_id_2: 1}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_matches(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        result = await _real_get_integration_counts(service, [uuid4()])

        assert result == {}

    @pytest.mark.asyncio
    async def test_excludes_null_management_credential_id(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        cred_id = uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [(None, 2), (cred_id, 3)]
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        result = await _real_get_integration_counts(service, [cred_id])

        assert result == {cred_id: 3}

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        mock_session.exec.side_effect = SQLAlchemyError("connection lost")

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        result = await _real_get_integration_counts(service, [uuid4()])

        assert result == {}


class TestIntegrationCountPopulation:
    """Tests that integration_count is populated on credential responses."""

    @pytest.mark.asyncio
    async def test_get_credential_populates_integration_count(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        basic_auth_type: CredentialType,
    ) -> None:
        cred_id = uuid4()
        credential = Credential(
            id=cred_id,
            name="My Cred",
            credential_type_id=basic_auth_type.id,
            secret_id=uuid4(),
            enabled=True,
            project_id=uuid4(),
            created_by=mock_user.id,
        )
        credential.credential_type = basic_auth_type

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session.exec.return_value = mock_result
        mock_session.get.return_value = basic_auth_type
        mock_secret_service.retrieve_secret.return_value = {"username": "u", "password": "p"}

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        with patch.object(service, "get_integration_counts", new_callable=AsyncMock, return_value={cred_id: 5}):
            result = await service.get_credential(cred_id)

        assert result.integration_count == 5

    @pytest.mark.asyncio
    async def test_list_credentials_populates_integration_count(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        basic_auth_type: CredentialType,
    ) -> None:
        cred_id = uuid4()
        cred_read = CredentialRead(
            id=cred_id,
            name="Listed Cred",
            credential_type_id=basic_auth_type.id,
            enabled=True,
            project_id=uuid4(),
            inputs={},
            created_by=mock_user.id,
        )

        mock_list_response = MagicMock()
        mock_list_response.resources = [cred_read]

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        with (
            patch.object(service, "list_resources", new_callable=AsyncMock, return_value=mock_list_response),
            patch.object(service, "get_integration_counts", new_callable=AsyncMock, return_value={cred_id: 2}),
        ):
            result = await service.list_credentials()

        assert result.resources[0].integration_count == 2


class TestValidateInputs:
    """Tests for _validate_inputs helper (T027)."""

    def test_valid_inputs_pass(self) -> None:
        _validate_inputs({"token": "abc"}, BEARER_TYPE_INPUTS)

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(CredentialValidationError, match="Unknown field"):
            _validate_inputs({"token": "abc", "bogus": "val"}, BEARER_TYPE_INPUTS)

    def test_missing_required_field_rejected(self) -> None:
        with pytest.raises(CredentialValidationError, match="Missing required"):
            _validate_inputs({}, BEARER_TYPE_INPUTS)

    def test_missing_one_of_multiple_required(self) -> None:
        with pytest.raises(CredentialValidationError, match="password"):
            _validate_inputs({"username": "admin"}, BASIC_AUTH_TYPE_INPUTS)

    def test_encrypted_sentinel_rejected_on_create(self) -> None:
        with pytest.raises(CredentialValidationError, match="reserved"):
            _validate_inputs({"token": ENCRYPTED_SENTINEL}, BEARER_TYPE_INPUTS)

    def test_encrypted_sentinel_allowed_on_patch(self) -> None:
        _validate_inputs(
            {"username": "admin", "password": ENCRYPTED_SENTINEL},
            BASIC_AUTH_TYPE_INPUTS,
            allow_sentinel=True,
        )

    def test_invalid_choice_rejected(self) -> None:
        choice_inputs = {
            "fields": [
                {
                    "id": "region",
                    "type": "string",
                    "secret": False,
                    "label": "Region",
                    "choices": ["us-east", "eu-west"],
                },
                {"id": "api_key", "type": "string", "secret": True, "label": "Key"},
            ],
            "required": ["api_key"],
        }
        with pytest.raises(CredentialValidationError, match="Invalid value"):
            _validate_inputs({"region": "invalid_region", "api_key": "key"}, choice_inputs)

    def test_valid_choice_accepted(self) -> None:
        choice_inputs = {
            "fields": [
                {
                    "id": "region",
                    "type": "string",
                    "secret": False,
                    "label": "Region",
                    "choices": ["us-east", "eu-west"],
                },
                {"id": "api_key", "type": "string", "secret": True, "label": "Key"},
            ],
            "required": ["api_key"],
        }
        _validate_inputs({"region": "us-east", "api_key": "key"}, choice_inputs)

    def test_payload_too_large_rejected(self) -> None:
        large_value = "x" * 70000
        with pytest.raises(CredentialValidationError, match="exceeds maximum size"):
            _validate_inputs({"token": large_value}, BEARER_TYPE_INPUTS)

    def test_empty_inputs_with_no_required_passes(self) -> None:
        no_required = {
            "fields": [{"id": "optional", "type": "string", "secret": False, "label": "Opt"}],
            "required": [],
        }
        _validate_inputs({}, no_required)

    def test_none_value_does_not_satisfy_required(self) -> None:
        with pytest.raises(CredentialValidationError, match="Missing required"):
            _validate_inputs({"token": None}, BEARER_TYPE_INPUTS)

    def test_required_skipped_in_patch_mode(self) -> None:
        # PATCH mode: missing required fields are OK (they're preserved from existing)
        _validate_inputs({}, BEARER_TYPE_INPUTS, allow_sentinel=True)

    def test_unknown_fields_still_rejected_in_patch_mode(self) -> None:
        with pytest.raises(CredentialValidationError, match="Unknown field"):
            _validate_inputs({"bogus": "val"}, BEARER_TYPE_INPUTS, allow_sentinel=True)

    def test_boolean_field_accepts_true(self) -> None:
        _validate_inputs({"verify_ssl": True}, BOOLEAN_TYPE_INPUTS)

    def test_boolean_field_accepts_false(self) -> None:
        _validate_inputs({"verify_ssl": False}, BOOLEAN_TYPE_INPUTS)

    def test_boolean_field_rejects_string(self) -> None:
        with pytest.raises(CredentialValidationError, match="must be a boolean"):
            _validate_inputs({"verify_ssl": "true"}, BOOLEAN_TYPE_INPUTS)

    def test_boolean_field_rejects_string_yes(self) -> None:
        with pytest.raises(CredentialValidationError, match="must be a boolean"):
            _validate_inputs({"verify_ssl": "yes"}, BOOLEAN_TYPE_INPUTS)

    def test_boolean_field_rejects_integer(self) -> None:
        with pytest.raises(CredentialValidationError, match="must be a boolean"):
            _validate_inputs({"verify_ssl": 1}, BOOLEAN_TYPE_INPUTS)

    def test_boolean_field_none_skipped(self) -> None:
        _validate_inputs({"verify_ssl": None}, BOOLEAN_TYPE_INPUTS)

    def test_boolean_field_sentinel_skipped(self) -> None:
        _validate_inputs({"verify_ssl": ENCRYPTED_SENTINEL}, BOOLEAN_TYPE_INPUTS, allow_sentinel=True)

    # --- String type validation ---

    def test_string_field_accepts_string(self) -> None:
        _validate_inputs({"token": "my-token"}, BEARER_TYPE_INPUTS)

    def test_string_field_rejects_dict(self) -> None:
        with pytest.raises(CredentialValidationError, match="must be a string"):
            _validate_inputs({"token": {"nested": "object"}}, BEARER_TYPE_INPUTS)

    def test_string_field_rejects_list(self) -> None:
        with pytest.raises(CredentialValidationError, match="must be a string"):
            _validate_inputs({"token": ["a", "b"]}, BEARER_TYPE_INPUTS)

    def test_string_field_rejects_integer(self) -> None:
        with pytest.raises(CredentialValidationError, match="must be a string"):
            _validate_inputs({"token": 12345}, BEARER_TYPE_INPUTS)

    # --- Host URL validation (AAP-74616 SSRF prevention) ---

    @pytest.mark.parametrize(
        "valid_host",
        [
            "https://controller.example.com",
            "https://controller.example.com:8443",
            "https://controller.example.com/",
            "https://192.168.1.1",
            "https://[::1]",
        ],
    )
    def test_host_valid_urls_accepted(self, valid_host: str) -> None:
        """Accept valid HTTPS host URLs including IPv4 and IPv6."""
        _validate_inputs({"host": valid_host}, HOST_TYPE_INPUTS)

    @pytest.mark.parametrize(
        ("invalid_host", "expected_match"),
        [
            ("https://evil.com/foo/bar/", "must not contain a path"),
            ("https://evil.com/foo/bar/?", "must not contain a path"),
            ("https://evil.com?x=1", "query string"),
            ("https://evil.com#frag", "fragment"),
            ("http://controller.example.com", "scheme must be https"),
        ],
    )
    def test_host_invalid_urls_rejected(self, invalid_host: str, expected_match: str) -> None:
        """Reject host URLs with paths, query strings, fragments, or wrong scheme."""
        with pytest.raises(CredentialValidationError, match=expected_match):
            _validate_inputs({"host": invalid_host}, HOST_TYPE_INPUTS)

    def test_host_http_accepted_when_setting_enabled(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Accept HTTP host URLs when credential_allow_http_host is enabled."""
        with override_settings(credential_allow_http_host=True):
            _validate_inputs({"host": "http://localhost:44927"}, HOST_TYPE_INPUTS)

    def test_host_http_rejected_when_setting_disabled(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Reject HTTP host URLs when credential_allow_http_host is disabled (default)."""
        with (
            override_settings(credential_allow_http_host=False),
            pytest.raises(CredentialValidationError, match="scheme must be https"),
        ):
            _validate_inputs({"host": "http://controller.example.com"}, HOST_TYPE_INPUTS)

    def test_host_sentinel_skipped(self) -> None:
        """Skip validation for $encrypted$ sentinel on PATCH."""
        _validate_inputs({"host": ENCRYPTED_SENTINEL}, HOST_TYPE_INPUTS, allow_sentinel=True)

    def test_host_none_skipped_on_patch(self) -> None:
        """Skip URL validation when host is None on PATCH (required-field check is separate)."""
        _validate_inputs({"host": None}, HOST_TYPE_INPUTS, allow_sentinel=True)

    def test_host_non_string_rejected(self) -> None:
        """Reject non-string host value."""
        with pytest.raises(CredentialValidationError, match="must be a string"):
            _validate_inputs({"host": 123}, HOST_TYPE_INPUTS)

    # --- Control character validation (AAP-79160) ---

    @pytest.mark.parametrize(
        ("payload", "description"),
        [
            ("valid\r\nX-Injected: evil", "CRLF header injection"),
            ("token\rX-Injected: evil", "CR-only header injection"),
            ("token\nX-Injected: evil", "LF-only header injection"),
            ("token\x00tail", "null byte injection"),
            ("abc\x01def", "SOH control character"),
            ("abc\x08def", "backspace control character"),
            ("abc\x1bdef", "escape control character"),
            ("abc\x7fdef", "DEL control character"),
        ],
    )
    def test_control_char_rejected(self, payload: str, description: str) -> None:
        """Reject control characters in single-line credential fields."""
        field_def: dict[str, Any] = {"id": "token", "label": "Token", "type": "string", "secret": True}
        with pytest.raises(CredentialValidationError, match="control character"):
            _validate_field_value("token", payload, field_def)

    def test_control_char_allows_normal_values(self) -> None:
        _validate_inputs({"token": "sk-abc123XYZ_-."}, BEARER_TYPE_INPUTS)

    def test_control_char_allows_tab(self) -> None:
        _validate_inputs({"token": "value\twith\ttabs"}, BEARER_TYPE_INPUTS)

    def test_control_char_allows_unicode(self) -> None:
        _validate_inputs({"token": "token-with-unicode-éèê"}, BEARER_TYPE_INPUTS)

    def test_crlf_rejected_via_validate_inputs(self) -> None:
        with pytest.raises(CredentialValidationError, match="control character"):
            _validate_inputs({"token": "abc\r\ndef"}, BEARER_TYPE_INPUTS)

    def test_null_byte_rejected_on_patch(self) -> None:
        with pytest.raises(CredentialValidationError, match="control character"):
            _validate_inputs({"token": "abc\x00def"}, BEARER_TYPE_INPUTS, allow_sentinel=True)

    def test_multiline_allows_newlines(self) -> None:
        """Multiline fields (e.g. SSH keys) allow CR/LF."""
        multiline_def = {"id": "cert", "label": "Certificate", "type": "string", "multiline": True}
        pem = "-----BEGIN CERTIFICATE-----\r\nbase64data\r\n-----END CERTIFICATE-----\r\n"
        _validate_field_value("cert", pem, multiline_def)

    def test_multiline_rejects_null_byte(self) -> None:
        """Multiline fields still reject null bytes and other dangerous control chars."""
        multiline_def = {"id": "cert", "label": "Certificate", "type": "string", "multiline": True}
        with pytest.raises(CredentialValidationError, match="control character"):
            _validate_field_value("cert", "BEGIN\x00END", multiline_def)

    def test_multiline_rejects_escape(self) -> None:
        multiline_def = {"id": "cert", "label": "Certificate", "type": "string", "multiline": True}
        with pytest.raises(CredentialValidationError, match="control character"):
            _validate_field_value("cert", "BEGIN\x1bEND", multiline_def)

    def test_crlf_header_injection_rejected_at_creation(self) -> None:
        with pytest.raises(CredentialValidationError):
            _validate_inputs({"token": "valid\r\nSet-Cookie: evil=1"}, BEARER_TYPE_INPUTS)


class TestFieldConstraints:
    """Tests for inter-field constraint validation (mutually_exclusive, required_one_of, required_together)."""

    def test_oauth_token_only_accepted(self) -> None:
        """Credential with only oauth_token passes validation."""
        _validate_inputs({"oauth_token": "tok"}, AAP_TYPE_INPUTS)

    def test_username_password_only_accepted(self) -> None:
        """Credential with only username+password passes validation."""
        _validate_inputs(
            {"username": "admin", "password": "secret"},
            AAP_TYPE_INPUTS,
        )

    def test_both_groups_rejected(self) -> None:
        """Credential with both oauth_token and username+password is rejected."""
        with pytest.raises(CredentialValidationError, match="mutually exclusive"):
            _validate_inputs(
                {
                    "oauth_token": "tok",
                    "username": "admin",
                    "password": "secret",
                },
                AAP_TYPE_INPUTS,
            )

    def test_no_auth_group_rejected_when_required(self) -> None:
        """Credential with neither auth method is rejected when require_one_group is True."""
        with pytest.raises(CredentialValidationError, match="At least one field group required"):
            _validate_inputs({}, AAP_TYPE_INPUTS)

    def test_partial_group_not_counted_as_populated(self) -> None:
        """Username without password triggers required_together, not required_one_of."""
        with pytest.raises(CredentialValidationError, match="must be provided together"):
            _validate_inputs(
                {"username": "admin"},
                AAP_TYPE_INPUTS,
            )

    def test_empty_string_not_counted_as_populated(self) -> None:
        """Empty string values do not count as populated."""
        with pytest.raises(CredentialValidationError, match="At least one field group required"):
            _validate_inputs(
                {"oauth_token": "", "username": "", "password": ""},
                AAP_TYPE_INPUTS,
            )

    def test_required_together_password_without_username(self) -> None:
        """Password without username triggers required_together error."""
        with pytest.raises(CredentialValidationError, match=r"must be provided together.*username"):
            _validate_inputs(
                {"password": "secret"},
                AAP_TYPE_INPUTS,
            )

    def test_sentinel_inputs_pass_validate_inputs_on_patch(self) -> None:
        """_validate_inputs allows sentinel values through on PATCH (constraint check deferred to merged state)."""
        _validate_inputs(
            {
                "oauth_token": "tok",
                "username": "admin",
                "password": ENCRYPTED_SENTINEL,
            },
            AAP_TYPE_INPUTS,
            allow_sentinel=True,
        )

    def test_merged_state_rejects_conflicting_groups(self) -> None:
        """Merged state with both auth groups populated is rejected by _validate_field_constraints."""
        merged = {
            "oauth_token": "tok",
            "username": "admin",
            "password": "secret",
        }
        with pytest.raises(CredentialValidationError, match="mutually exclusive"):
            _validate_field_constraints(merged, AAP_TYPE_INPUTS)

    def test_merged_state_accepts_single_group(self) -> None:
        """Merged state with one auth group fully populated and the other absent passes."""
        merged = {
            "oauth_token": "tok",
        }
        _validate_field_constraints(merged, AAP_TYPE_INPUTS)

    def test_patch_switch_from_token_to_basic_auth(self) -> None:
        """Switching auth method by clearing old group and providing new group passes."""
        merged = {"oauth_token": "", "username": "admin", "password": "secret"}
        _validate_field_constraints(merged, AAP_TYPE_INPUTS)

    def test_patch_switch_blocked_without_clearing_old_group(self) -> None:
        """Switching auth method without clearing old group is rejected."""
        merged = {
            "oauth_token": "existing-token",
            "username": "admin",
            "password": "secret",
        }
        with pytest.raises(CredentialValidationError, match="mutually exclusive"):
            _validate_field_constraints(merged, AAP_TYPE_INPUTS)

    def test_no_constraints_schema_skips_validation(self) -> None:
        """Types without constraint keys skip field constraint validation entirely."""
        _validate_inputs({"token": "abc"}, BEARER_TYPE_INPUTS)


class TestValidateSSHPrivateKey:
    """Tests for _validate_ssh_private_key helper."""

    @pytest.fixture
    def unprotected_ed25519_key(self) -> str:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

        key = ed25519.Ed25519PrivateKey.generate()
        return key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.OpenSSH,
            encryption_algorithm=NoEncryption(),
        ).decode("utf-8")

    @pytest.fixture
    def passphrase_protected_pem_key(self) -> str:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives.serialization import (
            BestAvailableEncryption,
            Encoding,
            PrivateFormat,
        )

        key = ed25519.Ed25519PrivateKey.generate()
        return key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=BestAvailableEncryption(b"testpassword"),
        ).decode("utf-8")

    @pytest.fixture
    def unprotected_pem_key(self) -> str:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

        key = ed25519.Ed25519PrivateKey.generate()
        return key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        ).decode("utf-8")

    def test_unprotected_key_accepted(self, unprotected_ed25519_key: str) -> None:
        _validate_ssh_private_key(unprotected_ed25519_key)

    def test_unprotected_pem_key_accepted(self, unprotected_pem_key: str) -> None:
        _validate_ssh_private_key(unprotected_pem_key)

    def test_passphrase_protected_key_rejected(self, passphrase_protected_pem_key: str) -> None:
        with pytest.raises(CredentialValidationError, match="passphrase-protected"):
            _validate_ssh_private_key(passphrase_protected_pem_key)

    def test_garbage_string_rejected(self) -> None:
        with pytest.raises(CredentialValidationError, match="Invalid SSH private key"):
            _validate_ssh_private_key("this is not a key")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(CredentialValidationError, match="Invalid SSH private key"):
            _validate_ssh_private_key("")

    def test_validate_inputs_ssh_field_calls_validation(self) -> None:
        with pytest.raises(CredentialValidationError, match="Invalid SSH private key"):
            _validate_inputs({"username": "deploy", "ssh_private_key": "garbage"}, SSH_TYPE_INPUTS)

    def test_validate_inputs_ssh_sentinel_skipped(self) -> None:
        _validate_inputs(
            {"username": "deploy", "ssh_private_key": ENCRYPTED_SENTINEL},
            SSH_TYPE_INPUTS,
            allow_sentinel=True,
        )


class TestAuditEventDispatch:
    """Tests that CredentialService dispatches audit events correctly."""

    @pytest.mark.asyncio
    async def test_create_dispatches_lifecycle_event(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        bearer_type: CredentialType,
    ) -> None:
        mock_session.get.side_effect = [None, bearer_type]
        project_id = uuid4()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_result.first.side_effect = [project_id, None]
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        data = CredentialCreate(
            name="test-cred",
            credential_type_id=bearer_type.id,
            inputs={"token": "sk-abc"},
            project_id=project_id,
        )

        with patch("syntara.credentials.services.credential_service.AuditEventDispatcher") as mock_dispatcher:
            await service.create_credential(data)

            mock_dispatcher.dispatch.assert_called_once()
            event = mock_dispatcher.dispatch.call_args[0][0]
            assert type(event).__name__ == "CredentialLifecycleEvent"
            assert event.action == "created"
            assert event.credential_name == "test-cred"

    @pytest.mark.asyncio
    async def test_update_dispatches_lifecycle_event(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        bearer_type: CredentialType,
    ) -> None:
        existing = Credential(
            id=uuid4(),
            name="old-name",
            credential_type_id=bearer_type.id,
            secret_id=uuid4(),
            project_id=uuid4(),
            enabled=True,
        )
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = existing
        mock_result.first.return_value = None
        mock_session.exec.return_value = mock_result
        mock_session.get.side_effect = [None, bearer_type]
        mock_secret_service.retrieve_secret.return_value = {"token": "sk-old"}

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        data = CredentialUpdate(name="new-name")

        with patch("syntara.credentials.services.credential_service.AuditEventDispatcher") as mock_dispatcher:
            await service.update_credential(existing.id, data)

            mock_dispatcher.dispatch.assert_called_once()
            event = mock_dispatcher.dispatch.call_args[0][0]
            assert type(event).__name__ == "CredentialLifecycleEvent"
            assert event.action == "updated"
            assert event.enabled_changed is False

    @pytest.mark.asyncio
    async def test_update_detects_enabled_changed(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        bearer_type: CredentialType,
    ) -> None:
        existing = Credential(
            id=uuid4(),
            name="my-cred",
            credential_type_id=bearer_type.id,
            secret_id=uuid4(),
            project_id=uuid4(),
            enabled=True,
        )
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = existing
        mock_session.exec.return_value = mock_result
        mock_session.get.side_effect = [None, bearer_type]
        mock_secret_service.retrieve_secret.return_value = {"token": "sk-val"}

        service = CredentialService(mock_session, mock_user, mock_secret_service)
        data = CredentialUpdate(enabled=False)

        with patch("syntara.credentials.services.credential_service.AuditEventDispatcher") as mock_dispatcher:
            await service.update_credential(existing.id, data)

            event = mock_dispatcher.dispatch.call_args[0][0]
            assert event.enabled_changed is True

    @pytest.mark.asyncio
    async def test_delete_dispatches_lifecycle_event_with_ref_count(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
    ) -> None:
        cred_id = uuid4()
        existing = Credential(
            id=cred_id,
            name="doomed-cred",
            credential_type_id=uuid4(),
            secret_id=uuid4(),
            project_id=uuid4(),
        )
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = existing
        mock_session.exec.return_value = mock_result

        service = CredentialService(mock_session, mock_user, mock_secret_service)

        with (
            patch.object(service, "get_workflow_counts", new_callable=AsyncMock, return_value={cred_id: 2}),
            patch("syntara.credentials.services.credential_service.AuditEventDispatcher") as mock_dispatcher,
        ):
            await service.delete_credential(cred_id)

            event = mock_dispatcher.dispatch.call_args[0][0]
            assert type(event).__name__ == "CredentialLifecycleEvent"
            assert event.action == "deleted"
            assert event.affected_workflow_count == 2
            assert event.credential_name == "doomed-cred"

    @pytest.mark.asyncio
    async def test_get_dispatches_encryption_failure_event(
        self,
        mock_session: MagicMock,
        mock_user: MagicMock,
        mock_secret_service: MagicMock,
        bearer_type: CredentialType,
    ) -> None:
        from syntara.credentials.exceptions import CredentialDecryptionError

        existing = Credential(
            id=uuid4(),
            name="broken-cred",
            credential_type_id=bearer_type.id,
            secret_id=uuid4(),
            project_id=uuid4(),
        )
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = existing
        mock_session.exec.return_value = mock_result
        mock_session.get.return_value = bearer_type

        service = CredentialService(mock_session, mock_user, mock_secret_service)

        with (
            patch.object(
                service, "_retrieve_or_empty", new_callable=AsyncMock, side_effect=CredentialDecryptionError("fail")
            ),
            patch("syntara.credentials.services.credential_service.AuditEventDispatcher") as mock_dispatcher,
        ):
            with pytest.raises(CredentialDecryptionError):
                await service.get_credential(existing.id)

            event = mock_dispatcher.dispatch.call_args[0][0]
            assert type(event).__name__ == "CredentialEncryptionFailureEvent"
            assert event.credential_name == "broken-cred"
            assert event.operation == "decrypt"


class TestLookupUsers:
    """Unit tests for CredentialService._lookup_users."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_uuids(
        self, mock_session: MagicMock, mock_user: MagicMock, mock_secret_service: MagicMock
    ) -> None:
        service = CredentialService(mock_session, mock_user, mock_secret_service)
        obj = MagicMock(created_by=None, updated_by=None)
        result = await service._lookup_users([obj])
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_user_map(
        self, mock_session: MagicMock, mock_user: MagicMock, mock_secret_service: MagicMock
    ) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "alice")])
        service = CredentialService(mock_session, mock_user, mock_secret_service)
        obj = MagicMock(created_by=uid, updated_by=None)
        result = await service._lookup_users([obj])
        assert result is not None
        assert result[uid] == (uid, "alice")

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self, mock_session: MagicMock, mock_user: MagicMock, mock_secret_service: MagicMock
    ) -> None:
        from sqlalchemy.exc import SQLAlchemyError

        uid = uuid4()
        mock_session.exec = AsyncMock(side_effect=SQLAlchemyError("db down"))
        service = CredentialService(mock_session, mock_user, mock_secret_service)
        obj = MagicMock(created_by=uid, updated_by=None)
        result = await service._lookup_users([obj])
        assert result is None


class TestResolveUserReferences:
    """Unit tests for CredentialService._resolve_user_references."""

    @pytest.mark.asyncio
    async def test_resolves_uuid_to_user_reference(
        self, mock_session: MagicMock, mock_user: MagicMock, mock_secret_service: MagicMock
    ) -> None:
        from syntara.core.models.user_reference import UserReference

        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "alice")])
        service = CredentialService(mock_session, mock_user, mock_secret_service)
        obj = MagicMock(created_by=uid, updated_by=uid)
        await service._resolve_user_references([obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.id == uid
        assert obj.created_by.name == "alice"
        assert isinstance(obj.updated_by, UserReference)

    @pytest.mark.asyncio
    async def test_sets_none_for_unresolvable_uuid(
        self, mock_session: MagicMock, mock_user: MagicMock, mock_secret_service: MagicMock
    ) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[])
        service = CredentialService(mock_session, mock_user, mock_secret_service)
        obj = MagicMock(created_by=uid, updated_by=None)
        await service._resolve_user_references([obj])
        assert obj.created_by is None

    @pytest.mark.asyncio
    async def test_sets_none_on_lookup_failure(
        self, mock_session: MagicMock, mock_user: MagicMock, mock_secret_service: MagicMock
    ) -> None:
        from sqlalchemy.exc import SQLAlchemyError

        uid = uuid4()
        mock_session.exec = AsyncMock(side_effect=SQLAlchemyError("db down"))
        service = CredentialService(mock_session, mock_user, mock_secret_service)
        obj = MagicMock(created_by=uid, updated_by=uid)
        await service._resolve_user_references([obj])
        assert obj.created_by is None
        assert obj.updated_by is None

    @pytest.mark.asyncio
    async def test_handles_multiple_objects(
        self, mock_session: MagicMock, mock_user: MagicMock, mock_secret_service: MagicMock
    ) -> None:
        from syntara.core.models.user_reference import UserReference

        uid1, uid2 = uuid4(), uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid1, "alice"), (uid2, "bob")])
        service = CredentialService(mock_session, mock_user, mock_secret_service)
        obj1 = MagicMock(created_by=uid1, updated_by=None)
        obj2 = MagicMock(created_by=uid2, updated_by=uid1)
        await service._resolve_user_references([obj1, obj2])
        assert isinstance(obj1.created_by, UserReference)
        assert obj1.created_by.name == "alice"
        assert isinstance(obj2.created_by, UserReference)
        assert obj2.created_by.name == "bob"
        assert isinstance(obj2.updated_by, UserReference)
        assert obj2.updated_by.name == "alice"
