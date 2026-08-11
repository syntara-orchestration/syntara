"""Tests for AAP credential resolution.

Tests the credential_resolver module which resolves Nexus credentials
to AAP authentication details for proxy endpoint authentication.
Non-sensitive connection details (URL, TLS) come from integration configuration.
"""

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest

from syntara.aap.auth import AAPConnection
from syntara.aap.credential_resolver import (
    AAP_CREDENTIAL_TYPE_NAME,
    _decrypt_credential_inputs,
    _extract_auth_from_extra_vars,
    _fetch_credential,
    _resolve_credential_injectors,
    _validate_credential_enabled,
    _validate_credential_id,
    _validate_credential_ownership,
    _validate_credential_type,
    resolve_aap_connection_from_credential,
)
from syntara.aap.exceptions import AAPAuthenticationError, AAPNotConfiguredError
from syntara.core.lib.encryption import EncryptionError

if TYPE_CHECKING:
    from syntara.credentials.models.credential import Credential
    from syntara.credentials.models.credential_type import CredentialType

# Sentinel object for default parameter handling
_DEFAULT_SENTINEL: object = object()


def _mock_credential_type(
    *,
    name: str = AAP_CREDENTIAL_TYPE_NAME,
    injectors: dict[str, Any] | None | object = _DEFAULT_SENTINEL,
) -> "CredentialType":
    """Create a mock CredentialType."""
    credential_type = MagicMock()
    credential_type.name = name
    # Handle injectors: use default dict, explicit value, or None
    if injectors == _DEFAULT_SENTINEL:
        credential_type.injectors = {
            "extra_vars": {
                "aap_oauth_token": "{{ oauth_token }}",
                "aap_username": "{{ username }}",
                "aap_password": "{{ password }}",
            }
        }
    else:
        credential_type.injectors = injectors
    return credential_type


def _mock_credential(
    *,
    credential_id: UUID | None = None,
    name: str = "Test AAP Credential",
    credential_type: "CredentialType | None | object" = _DEFAULT_SENTINEL,
    enabled: bool = True,
    secret_id: UUID | None | object = _DEFAULT_SENTINEL,
    created_by: UUID | None = None,
) -> "Credential":
    """Create a mock Credential."""
    credential = MagicMock()
    credential.id = credential_id or uuid4()
    credential.name = name
    # Handle credential_type: use default mock, explicit value, or None
    if credential_type == _DEFAULT_SENTINEL:
        credential.credential_type = _mock_credential_type()
    else:
        credential.credential_type = credential_type
    credential.enabled = enabled
    # Handle secret_id: use default UUID, explicit value, or None
    if secret_id == _DEFAULT_SENTINEL:
        credential.secret_id = uuid4()
    else:
        credential.secret_id = secret_id
    credential.created_by = created_by or uuid4()
    # Mock the is_owned_by method
    credential.is_owned_by = MagicMock(return_value=True)
    return credential


class TestValidateCredentialId:
    """Tests for _validate_credential_id helper."""

    def test_returns_uuid_when_uuid_provided(self) -> None:
        """Should return UUID unchanged when UUID is provided."""
        expected = uuid4()
        result = _validate_credential_id(expected)
        assert result == expected

    def test_converts_valid_uuid_string(self) -> None:
        """Should convert valid UUID string to UUID object."""
        uuid_str = "123e4567-e89b-12d3-a456-426614174000"
        result = _validate_credential_id(uuid_str)
        assert isinstance(result, UUID)
        assert str(result) == uuid_str

    def test_raises_on_invalid_uuid_string(self) -> None:
        """Should raise AAPAuthenticationError for invalid UUID format."""
        with pytest.raises(AAPAuthenticationError, match="Invalid credential_id format"):
            _validate_credential_id("not-a-uuid")

    def test_raises_with_credential_id_in_message(self) -> None:
        """Should include the invalid credential_id in error message."""
        invalid_id = "bad-format"
        with pytest.raises(AAPAuthenticationError, match=f"got '{invalid_id}'"):
            _validate_credential_id(invalid_id)


class TestFetchCredential:
    """Tests for _fetch_credential helper."""

    @pytest.mark.asyncio
    async def test_returns_credential_when_found(self) -> None:
        """Should return credential when it exists and is not deleted."""
        credential_id = uuid4()
        expected_credential = _mock_credential(credential_id=credential_id)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = expected_credential

        mock_session = AsyncMock()
        mock_session.exec.return_value = mock_result

        result = await _fetch_credential(mock_session, credential_id)

        assert result == expected_credential

    @pytest.mark.asyncio
    async def test_raises_when_credential_not_found(self) -> None:
        """Should raise AAPNotConfiguredError when credential doesn't exist."""
        credential_id = uuid4()

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.exec.return_value = mock_result

        with pytest.raises(AAPNotConfiguredError, match=f"Credential {credential_id} not found"):
            await _fetch_credential(mock_session, credential_id)


class TestValidateCredentialType:
    """Tests for _validate_credential_type helper."""

    def test_passes_for_correct_credential_type(self) -> None:
        """Should not raise when credential type is 'Ansible Automation Platform'."""
        credential = _mock_credential(credential_type=_mock_credential_type(name=AAP_CREDENTIAL_TYPE_NAME))
        _validate_credential_type(credential)  # Should not raise

    def test_raises_for_wrong_credential_type(self) -> None:
        """Should raise AAPNotConfiguredError for non-AAP credential type."""
        credential = _mock_credential(credential_type=_mock_credential_type(name="AWS"))

        with pytest.raises(AAPNotConfiguredError, match="Credential must be of type"):
            _validate_credential_type(credential)

    def test_raises_when_credential_type_is_none(self) -> None:
        """Should raise AAPNotConfiguredError when credential_type is None."""
        credential = _mock_credential(credential_type=None)

        with pytest.raises(AAPNotConfiguredError, match="got 'Unknown'"):
            _validate_credential_type(credential)

    def test_includes_actual_type_in_error_message(self) -> None:
        """Should include the actual credential type in error message."""
        credential = _mock_credential(credential_type=_mock_credential_type(name="GitHub"))

        with pytest.raises(AAPNotConfiguredError, match="got 'GitHub'"):
            _validate_credential_type(credential)


class TestValidateCredentialEnabled:
    """Tests for _validate_credential_enabled helper."""

    def test_passes_when_credential_is_enabled(self) -> None:
        """Should not raise when credential is enabled."""
        credential = _mock_credential(enabled=True)
        _validate_credential_enabled(credential)  # Should not raise

    def test_raises_when_credential_is_disabled(self) -> None:
        """Should raise AAPNotConfiguredError when credential is disabled."""
        credential = _mock_credential(name="My AAP Cred", enabled=False)

        with pytest.raises(AAPNotConfiguredError, match="Credential 'My AAP Cred' is disabled"):
            _validate_credential_enabled(credential)


class TestValidateCredentialOwnership:
    """Tests for _validate_credential_ownership helper."""

    def test_passes_when_user_owns_credential(self) -> None:
        """Should not raise when user is the credential owner."""
        from typing import cast

        user_id = uuid4()
        credential = _mock_credential()
        # Type assertion for mypy - cast credential to Any to allow method assignment
        cast("MagicMock", credential.is_owned_by).return_value = True

        _validate_credential_ownership(credential, user_id)  # Should not raise

        cast("MagicMock", credential.is_owned_by).assert_called_once_with(user_id)

    def test_raises_when_user_does_not_own_credential(self) -> None:
        """Should raise AAPAuthenticationError when user is not the owner."""
        from typing import cast

        user_id = uuid4()
        credential_id = uuid4()
        credential = _mock_credential(credential_id=credential_id)
        # Type assertion for mypy - cast credential to Any to allow method assignment
        cast("MagicMock", credential.is_owned_by).return_value = False

        with pytest.raises(AAPAuthenticationError, match=f"User {user_id} is not authorized"):
            _validate_credential_ownership(credential, user_id)


class TestDecryptCredentialInputs:
    """Tests for _decrypt_credential_inputs helper."""

    @pytest.mark.asyncio
    async def test_returns_decrypted_inputs(self) -> None:
        """Should return decrypted inputs from SecretService."""
        credential = _mock_credential()
        expected_inputs: dict[str, str | bool | int] = {
            "oauth_token": "secret-token",
        }

        mock_secret_service = AsyncMock()
        mock_secret_service.retrieve_secret.return_value = expected_inputs

        result = await _decrypt_credential_inputs(credential, mock_secret_service)

        assert result == expected_inputs
        mock_secret_service.retrieve_secret.assert_called_once_with(credential.secret_id)

    @pytest.mark.asyncio
    async def test_raises_when_no_secret_id(self) -> None:
        """Should raise AAPNotConfiguredError when credential has no secret_id."""
        credential = _mock_credential(name="Test Cred", secret_id=None)
        mock_secret_service = AsyncMock()

        with pytest.raises(AAPNotConfiguredError, match="Credential 'Test Cred' has no stored secret data"):
            await _decrypt_credential_inputs(credential, mock_secret_service)

    @pytest.mark.asyncio
    async def test_raises_on_decryption_failure(self) -> None:
        """Should raise AAPAuthenticationError when decryption fails."""
        credential = _mock_credential(name="Test Cred")

        mock_secret_service = AsyncMock()
        mock_secret_service.retrieve_secret.side_effect = EncryptionError("Decryption failed")

        with pytest.raises(AAPAuthenticationError, match="Failed to decrypt credential 'Test Cred'"):
            await _decrypt_credential_inputs(credential, mock_secret_service)


class TestResolveCredentialInjectors:
    """Tests for _resolve_credential_injectors helper."""

    def test_resolves_injector_templates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should resolve injector templates and return extra_vars."""
        decrypted_inputs: dict[str, str | bool | int] = {
            "oauth_token": "my-token",
        }
        expected_extra_vars: dict[str, str | bool | int] = {
            "aap_oauth_token": "my-token",
        }

        mock_resolved = MagicMock()
        mock_resolved.extra_vars = expected_extra_vars

        mock_injector_resolver = MagicMock()
        mock_injector_resolver.resolve.return_value = mock_resolved
        monkeypatch.setattr("syntara.aap.credential_resolver.InjectorResolver", mock_injector_resolver)

        credential = _mock_credential()

        result = _resolve_credential_injectors(credential, decrypted_inputs)

        assert result == expected_extra_vars
        assert credential.credential_type is not None  # Type narrowing for mypy
        mock_injector_resolver.resolve.assert_called_once_with(
            injectors=credential.credential_type.injectors,
            decrypted_inputs=decrypted_inputs,
        )

    def test_raises_when_no_injectors(self) -> None:
        """Should raise AAPNotConfiguredError when credential type has no injectors."""
        credential = _mock_credential(credential_type=_mock_credential_type(injectors=None))
        empty_inputs: dict[str, str | bool | int] = {}

        with pytest.raises(AAPNotConfiguredError, match="has no injector configuration"):
            _resolve_credential_injectors(credential, empty_inputs)

    def test_raises_when_credential_type_is_none(self) -> None:
        """Should raise AAPNotConfiguredError when credential_type is None."""
        credential = _mock_credential(credential_type=None)
        empty_inputs: dict[str, str | bool | int] = {}

        with pytest.raises(AAPNotConfiguredError, match="Credential type 'Unknown' has no injector configuration"):
            _resolve_credential_injectors(credential, empty_inputs)


class TestExtractAuthFromExtraVars:
    """Tests for _extract_auth_from_extra_vars helper."""

    def test_extracts_oauth_token_auth(self) -> None:
        """Should extract OAuth token authentication."""
        extra_vars: dict[str, str | bool | int] = {
            "aap_oauth_token": "my-oauth-token",
        }

        auth_headers, basic_auth = _extract_auth_from_extra_vars(extra_vars)

        assert dict(auth_headers) == {"authorization": "Bearer my-oauth-token"}
        assert basic_auth is None

    def test_extracts_basic_auth(self) -> None:
        """Should extract basic authentication when OAuth token not provided."""
        extra_vars: dict[str, str | bool | int] = {
            "aap_username": "admin",
            "aap_password": "password123",
        }

        auth_headers, basic_auth = _extract_auth_from_extra_vars(extra_vars)

        assert dict(auth_headers) == {}
        assert basic_auth is not None
        assert isinstance(basic_auth, httpx.BasicAuth)

    def test_prefers_oauth_over_basic_auth(self) -> None:
        """Should prefer OAuth token when both OAuth and basic auth are provided."""
        extra_vars: dict[str, str | bool | int] = {
            "aap_oauth_token": "my-token",
            "aap_username": "admin",
            "aap_password": "password123",
        }

        auth_headers, basic_auth = _extract_auth_from_extra_vars(extra_vars)

        assert "authorization" in dict(auth_headers)
        assert basic_auth is None

    def test_raises_when_missing_auth_credentials(self) -> None:
        """Should raise when neither OAuth token nor username+password provided."""
        extra_vars: dict[str, str | bool | int] = {}

        with pytest.raises(
            AAPAuthenticationError,
            match="Credential must provide either aap_oauth_token or aap_username\\+aap_password",
        ):
            _extract_auth_from_extra_vars(extra_vars)

    def test_raises_when_only_username_provided(self) -> None:
        """Should raise when username provided without password."""
        extra_vars: dict[str, str | bool | int] = {
            "aap_username": "admin",
        }

        with pytest.raises(AAPAuthenticationError, match="must provide either"):
            _extract_auth_from_extra_vars(extra_vars)

    def test_raises_when_only_password_provided(self) -> None:
        """Should raise when password provided without username."""
        extra_vars: dict[str, str | bool | int] = {
            "aap_password": "password123",
        }

        with pytest.raises(AAPAuthenticationError, match="must provide either"):
            _extract_auth_from_extra_vars(extra_vars)


class TestResolveAAPConnectionFromCredential:
    """Tests for resolve_aap_connection_from_credential main function."""

    @pytest.mark.asyncio
    async def test_successful_resolution_with_oauth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should successfully resolve AAP auth with OAuth token."""
        credential_id = uuid4()
        user_id = uuid4()
        credential = _mock_credential(credential_id=credential_id, created_by=user_id)

        # Mock database session
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session = AsyncMock()
        mock_session.exec.return_value = mock_result

        # Mock secret service
        decrypted_inputs: dict[str, str | bool | int] = {
            "oauth_token": "secret-token",
        }
        mock_secret_service = AsyncMock()
        mock_secret_service.retrieve_secret.return_value = decrypted_inputs

        mock_create_secret_service = MagicMock(return_value=mock_secret_service)
        monkeypatch.setattr("syntara.aap.credential_resolver.create_secret_service", mock_create_secret_service)

        # Mock InjectorResolver
        mock_resolved = MagicMock()
        extra_vars: dict[str, str | bool | int] = {
            "aap_oauth_token": "secret-token",
        }
        mock_resolved.extra_vars = extra_vars
        mock_injector_resolver = MagicMock()
        mock_injector_resolver.resolve.return_value = mock_resolved
        monkeypatch.setattr("syntara.aap.credential_resolver.InjectorResolver", mock_injector_resolver)

        result = await resolve_aap_connection_from_credential(mock_session, credential_id, user_id)

        assert isinstance(result, AAPConnection)
        assert result.base_url == ""
        assert result.headers == {"authorization": "Bearer secret-token"}
        assert result.basic_auth is None

    @pytest.mark.asyncio
    async def test_successful_resolution_with_basic_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should successfully resolve AAP auth with basic auth."""
        credential_id = uuid4()
        user_id = uuid4()
        credential = _mock_credential(credential_id=credential_id, created_by=user_id)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session = AsyncMock()
        mock_session.exec.return_value = mock_result

        decrypted_inputs: dict[str, str | bool | int] = {
            "username": "admin",
            "password": "pass123",
        }
        mock_secret_service = AsyncMock()
        mock_secret_service.retrieve_secret.return_value = decrypted_inputs

        mock_create_secret_service = MagicMock(return_value=mock_secret_service)
        monkeypatch.setattr("syntara.aap.credential_resolver.create_secret_service", mock_create_secret_service)

        mock_resolved = MagicMock()
        extra_vars_basic: dict[str, str | bool | int] = {
            "aap_username": "admin",
            "aap_password": "pass123",
        }
        mock_resolved.extra_vars = extra_vars_basic
        mock_injector_resolver = MagicMock()
        mock_injector_resolver.resolve.return_value = mock_resolved
        monkeypatch.setattr("syntara.aap.credential_resolver.InjectorResolver", mock_injector_resolver)

        result = await resolve_aap_connection_from_credential(mock_session, credential_id, user_id)

        assert isinstance(result, AAPConnection)
        assert result.basic_auth is not None
        assert isinstance(result.basic_auth, httpx.BasicAuth)

    @pytest.mark.asyncio
    async def test_accepts_string_credential_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should accept credential_id as string and convert to UUID."""
        credential_id = uuid4()
        user_id = uuid4()
        credential = _mock_credential(credential_id=credential_id, created_by=user_id)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session = AsyncMock()
        mock_session.exec.return_value = mock_result

        decrypted_inputs: dict[str, str | bool | int] = {"oauth_token": "token"}
        mock_secret_service = AsyncMock()
        mock_secret_service.retrieve_secret.return_value = decrypted_inputs

        mock_create_secret_service = MagicMock(return_value=mock_secret_service)
        monkeypatch.setattr("syntara.aap.credential_resolver.create_secret_service", mock_create_secret_service)

        mock_resolved = MagicMock()
        extra_vars_str: dict[str, str | bool | int] = {
            "aap_oauth_token": "token",
        }
        mock_resolved.extra_vars = extra_vars_str
        mock_injector_resolver = MagicMock()
        mock_injector_resolver.resolve.return_value = mock_resolved
        monkeypatch.setattr("syntara.aap.credential_resolver.InjectorResolver", mock_injector_resolver)

        # Pass credential_id as string
        result = await resolve_aap_connection_from_credential(mock_session, str(credential_id), user_id)

        assert isinstance(result, AAPConnection)

    @pytest.mark.asyncio
    async def test_raises_on_invalid_credential_id_format(self) -> None:
        """Should raise AAPAuthenticationError for invalid UUID format."""
        mock_session = AsyncMock()

        with pytest.raises(AAPAuthenticationError, match="Invalid credential_id format"):
            await resolve_aap_connection_from_credential(mock_session, "not-a-uuid", uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_credential_not_found(self) -> None:
        """Should raise AAPNotConfiguredError when credential doesn't exist."""
        credential_id = uuid4()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.exec.return_value = mock_result

        with pytest.raises(AAPNotConfiguredError, match="not found"):
            await resolve_aap_connection_from_credential(mock_session, credential_id, uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_wrong_credential_type(self) -> None:
        """Should raise AAPNotConfiguredError for non-AAP credential type."""
        credential_id = uuid4()
        user_id = uuid4()
        credential = _mock_credential(
            credential_id=credential_id,
            created_by=user_id,
            credential_type=_mock_credential_type(name="AWS"),
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session = AsyncMock()
        mock_session.exec.return_value = mock_result

        with pytest.raises(AAPNotConfiguredError, match="Credential must be of type"):
            await resolve_aap_connection_from_credential(mock_session, credential_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_when_credential_disabled(self) -> None:
        """Should raise AAPNotConfiguredError when credential is disabled."""
        credential_id = uuid4()
        user_id = uuid4()
        credential = _mock_credential(credential_id=credential_id, created_by=user_id, enabled=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session = AsyncMock()
        mock_session.exec.return_value = mock_result

        with pytest.raises(AAPNotConfiguredError, match="is disabled"):
            await resolve_aap_connection_from_credential(mock_session, credential_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_when_user_not_authorized(self) -> None:
        """Should raise AAPAuthenticationError when user doesn't own credential."""
        from typing import cast

        credential_id = uuid4()
        user_id = uuid4()
        other_user_id = uuid4()
        credential = _mock_credential(credential_id=credential_id, created_by=other_user_id)
        # Type assertion for mypy - cast credential to Any to allow method assignment
        cast("MagicMock", credential.is_owned_by).return_value = False

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = credential
        mock_session = AsyncMock()
        mock_session.exec.return_value = mock_result

        with pytest.raises(AAPAuthenticationError, match="is not authorized"):
            await resolve_aap_connection_from_credential(mock_session, credential_id, user_id)
