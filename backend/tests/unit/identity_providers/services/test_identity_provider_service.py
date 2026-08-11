"""Unit tests for IdentityProviderService.

Tests cover:
- CRUD operations (create, get, patch, delete)
- Duplicate name handling (_is_duplicate_name_error)
- Group mapping entry extraction (_extract_group_mapping_entries)
- Configuration patch merging (preserving unset fields)
- Soft-delete cascade (identity cleanup, session revocation, secret deletion)
- get_decrypted_config
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from syntara.identity_providers.exceptions import (
    IdentityProviderNameConflictError,
    IdentityProviderNotFoundError,
)
from syntara.identity_providers.models.identity_provider import (
    IdentityProvider,
    IdentityProviderCreate,
    IdentityProviderPatch,
)
from syntara.identity_providers.models.identity_provider_configuration import (
    OIDCClaimMapping,
    OIDCConfiguration,
    OIDCConfigurationPatch,
    OIDCConfigurationResponse,
    OIDCGroupMappingEntry,
)
from syntara.identity_providers.services.identity_provider_service import (
    IdentityProviderService,
)


def _make_oidc_config(**overrides: object) -> OIDCConfiguration:
    """Build an OIDCConfiguration with sensible defaults."""
    defaults = {
        "issuer_url": "https://idp.example.com",
        "client_id": "nexus-client",
        "client_secret": "super-secret",
        "redirect_uri": "http://localhost:3000/auth/callback",
    }
    return OIDCConfiguration(**(defaults | overrides))


def _make_mock_secret_service() -> MagicMock:
    """Create a mock SecretService with standard async methods."""
    service = MagicMock()
    service.create_secret = AsyncMock(return_value=uuid4())
    service.retrieve_secret = AsyncMock(return_value={"client_secret": "super-secret"})
    service.update_secret = AsyncMock()
    service.delete_secret = AsyncMock()
    return service


def _make_mock_session() -> MagicMock:
    """Create a mock AsyncSession."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    session.exec = AsyncMock()
    return session


def _make_mock_user() -> MagicMock:
    """Create a mock User."""
    user = MagicMock()
    user.id = uuid4()
    return user


def _make_provider(**overrides: object) -> IdentityProvider:
    """Build an IdentityProvider DB model with sensible defaults."""
    provider_id = overrides.pop("id", uuid4())
    user_id = overrides.pop("user_id", uuid4())
    defaults: dict[str, object] = {
        "id": provider_id,
        "name": "Test IdP",
        "description": None,
        "enabled": True,
        "configuration": OIDCConfigurationResponse(
            issuer_url="https://idp.example.com",
            client_id="nexus-client",
            redirect_uri="http://localhost:3000/auth/callback",
        ),
        "secret_id": uuid4(),
        "created_by": user_id,
        "updated_by": user_id,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "labels": {},
    }
    defaults.update(overrides)
    return IdentityProvider(**defaults)


def _make_service(
    session: MagicMock | None = None,
    user: MagicMock | None = None,
    secret_service: MagicMock | None = None,
) -> IdentityProviderService:
    """Build a service with mock dependencies."""
    return IdentityProviderService(
        session or _make_mock_session(),
        user or _make_mock_user(),
        secret_service or _make_mock_secret_service(),
    )


# ============================================================================
# Create tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_provider_calls_store_config_and_flush() -> None:
    """Create stores secrets, adds to session, and flushes."""
    mock_session = _make_mock_session()
    mock_secret = _make_mock_secret_service()
    mock_user = _make_mock_user()

    # Mock session.exec to return empty list for group mapping query
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    mock_result.all.return_value = []
    mock_session.exec = AsyncMock(return_value=mock_result)

    service = _make_service(mock_session, mock_user, mock_secret)
    config = _make_oidc_config()
    create = IdentityProviderCreate(name="My IdP", configuration=config)

    response = await service.create_provider(create)

    assert response.name == "My IdP"
    assert response.enabled is True
    mock_secret.create_secret.assert_called_once()
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_provider_duplicate_name_raises_conflict() -> None:
    """IntegrityError with duplicate name is translated to IdentityProviderNameConflictError."""
    mock_session = _make_mock_session()
    mock_session.flush = AsyncMock(
        side_effect=IntegrityError("ix_identity_providers_name_unique violated", None, BaseException())
    )
    service = _make_service(mock_session)

    with pytest.raises(IdentityProviderNameConflictError):
        await service.create_provider(IdentityProviderCreate(name="DupIdP", configuration=_make_oidc_config()))


@pytest.mark.asyncio
async def test_create_provider_unrelated_integrity_error_re_raised() -> None:
    """IntegrityError unrelated to name duplication is re-raised as IntegrityError."""
    mock_session = _make_mock_session()
    mock_session.flush = AsyncMock(
        side_effect=IntegrityError("foreign key constraint on foo_id", None, BaseException())
    )
    service = _make_service(mock_session)

    with pytest.raises(IntegrityError):
        await service.create_provider(IdentityProviderCreate(name="SomeIdP", configuration=_make_oidc_config()))


# ============================================================================
# Get tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_provider_success() -> None:
    """Get a provider by ID returns the response."""
    provider = _make_provider(name="GetTest")
    mock_session = _make_mock_session()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = provider
    # Second call for group mapping entries
    mock_result_entries = MagicMock()
    mock_result_entries.all.return_value = []
    mock_session.exec = AsyncMock(side_effect=[mock_result, mock_result_entries])

    service = _make_service(mock_session)
    response = await service.get_provider(provider.id)

    assert response.id == provider.id
    assert response.name == "GetTest"


@pytest.mark.asyncio
async def test_get_provider_not_found_raises() -> None:
    """Getting a non-existent provider should raise IdentityProviderNotFoundError."""
    mock_session = _make_mock_session()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    mock_session.exec = AsyncMock(return_value=mock_result)

    service = _make_service(mock_session)

    with pytest.raises(IdentityProviderNotFoundError):
        await service.get_provider(uuid4())


# ============================================================================
# Patch tests
# ============================================================================


@pytest.mark.asyncio
async def test_patch_provider_name() -> None:
    """Patching only the name should preserve other fields."""
    provider = _make_provider(name="OriginalName", description="original desc")
    mock_session = _make_mock_session()

    # First exec: find the provider for patch
    mock_result_find = MagicMock()
    mock_result_find.one_or_none.return_value = provider
    # Second exec: find the provider for get_provider (after flush)
    mock_result_get = MagicMock()
    mock_result_get.one_or_none.return_value = provider
    # Third exec: load group mapping entries
    mock_result_entries = MagicMock()
    mock_result_entries.all.return_value = []

    mock_session.exec = AsyncMock(side_effect=[mock_result_find, mock_result_get, mock_result_entries])

    service = _make_service(mock_session)
    response = await service.patch_provider(
        provider.id,
        IdentityProviderPatch(name="UpdatedName"),
    )

    assert response.name == "UpdatedName"
    assert response.description == "original desc"


@pytest.mark.asyncio
async def test_patch_provider_not_found_raises() -> None:
    """Patching a non-existent provider should raise IdentityProviderNotFoundError."""
    mock_session = _make_mock_session()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    mock_session.exec = AsyncMock(return_value=mock_result)

    service = _make_service(mock_session)

    with pytest.raises(IdentityProviderNotFoundError):
        await service.patch_provider(uuid4(), IdentityProviderPatch(name="Ghost"))


@pytest.mark.asyncio
async def test_patch_provider_configuration_preserves_claim_mapping() -> None:
    """Patching config without claim_mapping preserves the existing one."""
    custom_mapping = OIDCClaimMapping(subject="sub", email="mail", username="upn", first_name="displayName")
    config = OIDCConfigurationResponse(
        issuer_url="https://idp.example.com",
        client_id="nexus-client",
        redirect_uri="http://localhost:3000/auth/callback",
        claim_mapping=custom_mapping,
    )
    provider = _make_provider(name="PreserveMapping", configuration=config)

    mock_session = _make_mock_session()
    mock_result_find = MagicMock()
    mock_result_find.one_or_none.return_value = provider
    mock_result_get = MagicMock()
    mock_result_get.one_or_none.return_value = provider
    mock_result_entries = MagicMock()
    mock_result_entries.all.return_value = []
    mock_session.exec = AsyncMock(side_effect=[mock_result_find, mock_result_get, mock_result_entries])

    service = _make_service(mock_session)
    patch_config = OIDCConfigurationPatch(
        issuer_url="https://new-issuer.example.com",
        client_id="new-client",
        redirect_uri="http://localhost:3000/auth/callback",
        enable_rp_initiated_logout=False,
    )
    response = await service.patch_provider(
        provider.id,
        IdentityProviderPatch(configuration=patch_config),
    )

    # claim_mapping should be preserved from original
    assert response.configuration.claim_mapping.username == "upn"
    assert response.configuration.claim_mapping.email == "mail"


@pytest.mark.asyncio
async def test_patch_provider_configuration_preserves_jmespath() -> None:
    """Patching config without group_jmespath_expression preserves the existing one."""
    config = OIDCConfigurationResponse(
        issuer_url="https://idp.example.com",
        client_id="nexus-client",
        redirect_uri="http://localhost:3000/auth/callback",
        group_jmespath_expression="token.groups",
    )
    provider = _make_provider(name="PreserveJmes", configuration=config)

    mock_session = _make_mock_session()
    mock_result_find = MagicMock()
    mock_result_find.one_or_none.return_value = provider
    mock_result_get = MagicMock()
    mock_result_get.one_or_none.return_value = provider
    mock_result_entries = MagicMock()
    mock_result_entries.all.return_value = []
    mock_session.exec = AsyncMock(side_effect=[mock_result_find, mock_result_get, mock_result_entries])

    service = _make_service(mock_session)
    patch_config = OIDCConfigurationPatch(
        issuer_url="https://new.example.com",
        client_id="new-client",
        redirect_uri="http://localhost:3000/auth/callback",
        enable_rp_initiated_logout=False,
    )
    response = await service.patch_provider(
        provider.id,
        IdentityProviderPatch(configuration=patch_config),
    )

    assert response.configuration.group_jmespath_expression == "token.groups"


# ============================================================================
# Delete tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_provider_success() -> None:
    """Delete hard-deletes the provider, cleans identities, revokes sessions, deletes secret."""
    provider = _make_provider(name="ToDelete")
    mock_session = _make_mock_session()
    mock_secret = _make_mock_secret_service()

    mock_find_result = MagicMock()
    mock_find_result.one_or_none.return_value = provider

    mock_identity_delete = MagicMock()
    mock_identity_delete.rowcount = 0
    mock_memberships_delete = MagicMock()
    mock_memberships_delete.rowcount = 0
    mock_tracking_delete = MagicMock()
    mock_tracking_delete.rowcount = 0

    mock_session.exec = AsyncMock(
        side_effect=[mock_find_result, mock_identity_delete, mock_memberships_delete, mock_tracking_delete]
    )

    service = _make_service(mock_session, secret_service=mock_secret)

    with patch("syntara.identity_providers.services.identity_provider_service.create_session_store") as mock_store_cls:
        mock_store = AsyncMock()
        mock_store.revoke_by_idp = AsyncMock(return_value=0)
        mock_store_cls.return_value = mock_store

        await service.delete_provider(provider.id)

    # Verify operation ordering: add → flush → delete → commit
    mock_session.add.assert_called_once_with(provider)
    mock_session.flush.assert_called_once()
    mock_session.delete.assert_called_once_with(provider)
    mock_session.commit.assert_called_once()
    calls = mock_session.method_calls
    call_names = [c[0] for c in calls]
    assert call_names.index("add") < call_names.index("flush") < call_names.index("delete") < call_names.index("commit")
    mock_secret.delete_secret.assert_called_once()


@pytest.mark.asyncio
async def test_delete_provider_not_found_raises() -> None:
    """Deleting a non-existent provider should raise IdentityProviderNotFoundError."""
    mock_session = _make_mock_session()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    mock_session.exec = AsyncMock(return_value=mock_result)

    service = _make_service(mock_session)

    with pytest.raises(IdentityProviderNotFoundError):
        await service.delete_provider(uuid4())


@pytest.mark.asyncio
async def test_delete_provider_revokes_sessions_and_deletes_identities() -> None:
    """Delete cleans up linked identities and revokes sessions."""
    provider = _make_provider(name="CascadeTest")
    mock_session = _make_mock_session()
    mock_secret = _make_mock_secret_service()

    mock_find_result = MagicMock()
    mock_find_result.one_or_none.return_value = provider

    mock_identity_delete = MagicMock()
    mock_identity_delete.rowcount = 3
    mock_memberships_delete = MagicMock()
    mock_memberships_delete.rowcount = 1
    mock_tracking_delete = MagicMock()
    mock_tracking_delete.rowcount = 1

    mock_session.exec = AsyncMock(
        side_effect=[
            mock_find_result,
            mock_identity_delete,
            mock_memberships_delete,
            mock_tracking_delete,
        ]
    )

    service = _make_service(mock_session, secret_service=mock_secret)

    with patch("syntara.identity_providers.services.identity_provider_service.create_session_store") as mock_store_cls:
        mock_store = AsyncMock()
        mock_store.revoke_by_idp = AsyncMock(return_value=5)
        mock_store_cls.return_value = mock_store

        await service.delete_provider(provider.id)

    # 4 exec calls: find provider, identity delete, delete sole-source memberships, delete tracking rows
    assert mock_session.exec.call_count == 4
    # Sessions should have been revoked
    mock_store.revoke_by_idp.assert_called_once_with(str(provider.id))


@pytest.mark.asyncio
async def test_delete_provider_without_secret_skips_secret_deletion() -> None:
    """Delete works when provider has no secret (secret_id=None)."""
    provider = _make_provider(name="NoSecret", secret_id=None)
    mock_session = _make_mock_session()
    mock_secret = _make_mock_secret_service()

    mock_find_result = MagicMock()
    mock_find_result.one_or_none.return_value = provider

    mock_identity_delete = MagicMock()
    mock_identity_delete.rowcount = 0
    mock_memberships_delete = MagicMock()
    mock_memberships_delete.rowcount = 0
    mock_tracking_delete = MagicMock()
    mock_tracking_delete.rowcount = 0

    mock_session.exec = AsyncMock(
        side_effect=[mock_find_result, mock_identity_delete, mock_memberships_delete, mock_tracking_delete]
    )

    service = _make_service(mock_session, secret_service=mock_secret)

    with patch("syntara.identity_providers.services.identity_provider_service.create_session_store") as mock_store_cls:
        mock_store = AsyncMock()
        mock_store.revoke_by_idp = AsyncMock(return_value=0)
        mock_store_cls.return_value = mock_store

        await service.delete_provider(provider.id)

    mock_secret.delete_secret.assert_not_called()
    mock_session.delete.assert_called_once_with(provider)


# ============================================================================
# Group mapping entry extraction tests
# ============================================================================


def test_extract_group_mapping_entries_empty() -> None:
    """Extracting entries from config with no entries returns empty list."""
    config = _make_oidc_config()
    entries = IdentityProviderService._extract_group_mapping_entries(config)
    assert entries == []


def test_extract_group_mapping_entries_populated() -> None:
    """Extracting entries from config with entries returns them."""
    group_id = uuid4()
    entries_in = [OIDCGroupMappingEntry(idp_group_value="role-a", nexus_group_id=group_id)]
    config = _make_oidc_config(group_mapping_entries=entries_in)
    entries_out = IdentityProviderService._extract_group_mapping_entries(config)
    assert len(entries_out) == 1
    assert entries_out[0].idp_group_value == "role-a"


def test_extract_group_mapping_entries_empty_list() -> None:
    """Extracting from config with empty list returns empty list."""
    config = _make_oidc_config(group_mapping_entries=[])
    entries = IdentityProviderService._extract_group_mapping_entries(config)
    assert entries == []


# ============================================================================
# Duplicate name detection tests
# ============================================================================


def test_is_duplicate_name_error_constraint_name() -> None:
    """Detects the constraint name in the error string."""
    service = IdentityProviderService.__new__(IdentityProviderService)
    e = IntegrityError("ix_identity_providers_name_unique violated", None, BaseException())
    assert service._is_duplicate_name_error(e) is True


def test_is_duplicate_name_error_table_column() -> None:
    """Detects identity_providers.name in error string."""
    service = IdentityProviderService.__new__(IdentityProviderService)
    e = IntegrityError("identity_providers.name constraint violation", None, BaseException())
    assert service._is_duplicate_name_error(e) is True


def test_is_duplicate_name_error_duplicate_key() -> None:
    """Detects duplicate key ... name pattern."""
    service = IdentityProviderService.__new__(IdentityProviderService)
    e = IntegrityError("Duplicate Key violation on column name", None, BaseException())
    assert service._is_duplicate_name_error(e) is True


def test_is_duplicate_name_error_unrelated() -> None:
    """Unrelated errors should not match."""
    service = IdentityProviderService.__new__(IdentityProviderService)
    e = IntegrityError("foreign key constraint on provider_id", None, BaseException())
    assert service._is_duplicate_name_error(e) is False


# ============================================================================
# get_decrypted_config test
# ============================================================================


@pytest.mark.asyncio
async def test_get_decrypted_config() -> None:
    """get_decrypted_config should return config with decrypted client_secret."""
    secret_id = uuid4()
    mock_secret = _make_mock_secret_service()
    mock_secret.retrieve_secret = AsyncMock(return_value={"client_secret": "my-secret"})

    service = _make_service(secret_service=mock_secret)

    config_data = OIDCConfigurationResponse(
        issuer_url="https://idp.example.com",
        client_id="nexus-client",
        redirect_uri="http://localhost:3000/auth/callback",
    )
    provider = _make_provider(name="DecryptTest", configuration=config_data, secret_id=secret_id)

    config = await service.get_decrypted_config(provider)

    assert config.client_secret == "my-secret"  # noqa: S105
    assert str(config.issuer_url) == "https://idp.example.com/"
    mock_secret.retrieve_secret.assert_called_once_with(secret_id)
