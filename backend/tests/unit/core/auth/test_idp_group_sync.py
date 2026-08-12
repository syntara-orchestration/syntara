# ruff: noqa: S106
"""Unit tests for IdP group sync on OIDC login."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import jmespath
import pytest

from syntara.auth.services.idp_group_sync import extract_idp_group_values, match_group_entries, sync_idp_groups
from syntara.core.models import User, UserIdentity
from syntara.identity_providers.models.identity_provider_configuration import (
    OIDCConfiguration,
    OIDCGroupMappingEntry,
    OIDCIdpType,
)
from syntara.identity_providers.models.idp_group_mapping import IdpGroupMappingEntry


def _make_user() -> User:
    return User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        is_enabled=True,
    )


def _make_identity(user: User, provider_id: UUID) -> UserIdentity:
    return UserIdentity(
        id=uuid4(),
        user_id=user.id,
        identity_provider_id=provider_id,
        issuer="https://idp.example.com",
        subject="sub-123",
    )


def _make_config(
    group_jmespath_expression: str | None = None,
    *,
    aap_role_mapping_enabled: bool = False,
    idp_type: str | None = None,
    allow_all_authenticated: bool = False,
) -> OIDCConfiguration:
    return OIDCConfiguration(
        provider_type="oidc",
        issuer_url="https://idp.example.com",
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="http://localhost:8000/callback",
        group_jmespath_expression=group_jmespath_expression,
        aap_role_mapping_enabled=aap_role_mapping_enabled,
        idp_type=idp_type,
        allow_all_authenticated=allow_all_authenticated,
    )


def _make_db_entry(provider_id: UUID, idp_group_value: str, nexus_group_id: UUID) -> IdpGroupMappingEntry:
    """Create an IdpGroupMappingEntry row as returned from the DB."""
    return IdpGroupMappingEntry(
        id=uuid4(),
        identity_provider_id=provider_id,
        idp_group_value=idp_group_value,
        nexus_group_id=nexus_group_id,
    )


def _make_mock_db(
    mapping_entries: list[IdpGroupMappingEntry] | None = None,
    users_group: MagicMock | None = None,
) -> AsyncMock:
    """Create a mock db session.

    The first call to db.exec returns the mapping entries (for the
    IdpGroupMappingEntry query). If ``users_group`` is provided, the second
    call returns it (for ``_resolve_users_group``). Remaining calls return
    empty results.
    """
    db = AsyncMock()

    entries = mapping_entries or []
    mapping_result = MagicMock()
    mapping_result.all = MagicMock(return_value=entries)

    users_group_result = MagicMock()
    users_group_result.first = MagicMock(return_value=users_group)

    def _make_empty_result() -> MagicMock:
        r = MagicMock()
        r.__iter__ = MagicMock(return_value=iter([]))
        r.first = MagicMock(return_value=None)
        r.all = MagicMock(return_value=[])
        return r

    call_count = 0

    async def _exec_side_effect(*args: object, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mapping_result
        if call_count == 2 and users_group is not None:
            return users_group_result
        return _make_empty_result()

    db.exec = AsyncMock(side_effect=_exec_side_effect)
    return db


class TestExtractIdpGroupValues:
    """Tests for the extract_idp_group_values function."""

    def test_escapes_control_chars_in_group_values(self) -> None:
        user_id = uuid4()
        claims = {"groups": ["admin", "dev\nops", "test\r\ngroup"]}
        result = extract_idp_group_values("groups", claims, user_id)
        assert result == {"admin", "dev\\nops", "test\\r\\ngroup"}

    def test_clean_group_values_unchanged(self) -> None:
        user_id = uuid4()
        claims = {"groups": ["admin", "developers", "ops"]}
        result = extract_idp_group_values("groups", claims, user_id)
        assert result == {"admin", "developers", "ops"}

    def test_rejects_string_claim_with_wildcard_expression(self) -> None:
        user_id = uuid4()
        claims = {"groups": "nexus-users"}
        result = extract_idp_group_values("groups[*]", claims, user_id)
        assert result is None

    def test_rejects_numeric_claim_with_wildcard_expression(self) -> None:
        user_id = uuid4()
        claims = {"groups": 42}
        result = extract_idp_group_values("groups[*]", claims, user_id)
        assert result is None

    def test_rejects_nested_string_claim_with_wildcard_expression(self) -> None:
        user_id = uuid4()
        claims = {"realm_access": {"roles": "admin"}}
        result = extract_idp_group_values("realm_access.roles[*]", claims, user_id)
        assert result is None

    def test_absent_claim_returns_empty_with_wildcard_expression(self) -> None:
        user_id = uuid4()
        claims = {"sub": "user-123"}
        result = extract_idp_group_values("groups[*]", claims, user_id)
        assert result == set()

    def test_dict_claim_not_rejected_with_wildcard_expression(self) -> None:
        user_id = uuid4()
        claims = {"groups": {"nested": "value"}}
        result = extract_idp_group_values("groups[*]", claims, user_id)
        assert result == set()

    def test_rejects_empty_string_claim_with_wildcard_expression(self) -> None:
        user_id = uuid4()
        claims = {"groups": ""}
        result = extract_idp_group_values("groups[*]", claims, user_id)
        assert result is None

    def test_fallback_jmespath_error_returns_empty_set(self) -> None:
        """When the base expression (without [*]) raises a JMESPath error, fall through to empty set."""
        from unittest.mock import patch

        user_id = uuid4()
        claims = {"groups": "admin"}
        call_count = 0
        original_search = jmespath.search

        def _search_side_effect(expr: str, data: object) -> object:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_search(expr, data)
            msg = "simulated error"
            raise jmespath.exceptions.JMESPathError(msg)

        with patch("syntara.auth.services.idp_group_sync.jmespath.search", side_effect=_search_side_effect):
            result = extract_idp_group_values("groups[*]", claims, user_id)
        assert result == set()

    def test_scalar_without_wildcard_still_works(self) -> None:
        user_id = uuid4()
        claims = {"role": "admin"}
        result = extract_idp_group_values("role", claims, user_id)
        assert result == {"admin"}


class TestSyncIdpGroups:
    """Tests for the sync_idp_groups function."""

    @pytest.mark.asyncio
    async def test_denies_when_no_group_mapping(self):
        """Should return False and clean up stale IdP groups when no entries exist."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        config = _make_config(group_jmespath_expression=None)
        db = _make_mock_db(mapping_entries=[])

        result = await sync_idp_groups(db, user, identity, {"groups": ["admin"]}, config)
        assert result is False
        assert db.exec.call_count > 1

    @pytest.mark.asyncio
    async def test_denies_when_no_mapping_entries(self):
        """Should return False and clean up stale IdP groups when no entries exist."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        config = _make_config(group_jmespath_expression="groups[*]")
        db = _make_mock_db(mapping_entries=[])

        result = await sync_idp_groups(db, user, identity, {"groups": ["admin"]}, config)
        assert result is False
        assert db.exec.call_count > 1

    def test_rejects_invalid_jmespath_at_config_time(self):
        """Should reject syntactically invalid JMESPath at model validation time."""
        with pytest.raises(ValueError, match="not a valid JMESPath expression"):
            _make_config(group_jmespath_expression="[[[invalid")

    @pytest.mark.asyncio
    async def test_denies_login_on_jmespath_runtime_error(self):
        """Should return False when JMESPath extraction fails at runtime."""
        from unittest.mock import patch

        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        config = _make_config(group_jmespath_expression="groups[*]")
        db = _make_mock_db(mapping_entries=[_make_db_entry(provider_id, "admin", nexus_group_id)])

        # Simulate a JMESPath runtime error (e.g., corrupted claims object)
        with patch("syntara.auth.services.idp_group_sync.jmespath.search", side_effect=TypeError("unexpected type")):
            result = await sync_idp_groups(db, user, identity, {"groups": ["admin"]}, config)
        assert result is False
        # Should only have the mapping entries query, no sync queries
        assert db.exec.call_count == 1

    @pytest.mark.asyncio
    async def test_processes_matching_groups(self):
        """Should return True and execute DB operations when groups match."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        config = _make_config(group_jmespath_expression="groups[*]")
        db = _make_mock_db(mapping_entries=[_make_db_entry(provider_id, "admin", nexus_group_id)])

        result = await sync_idp_groups(db, user, identity, {"groups": ["admin", "users"]}, config)
        assert result is True
        assert db.exec.call_count > 1

    @pytest.mark.asyncio
    async def test_handles_nested_jmespath(self):
        """Should handle nested JMESPath expressions like realm_access.roles[*]."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        config = _make_config(group_jmespath_expression="realm_access.roles[*]")
        db = _make_mock_db(mapping_entries=[_make_db_entry(provider_id, "admin", nexus_group_id)])

        await sync_idp_groups(
            db,
            user,
            identity,
            {"realm_access": {"roles": ["admin", "user"]}},
            config,
        )
        assert db.exec.call_count > 1

    @pytest.mark.asyncio
    async def test_returns_false_when_no_groups_match(self):
        """Should return False when mappings exist but none match the user's groups."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        config = _make_config(group_jmespath_expression="groups[*]")
        db = _make_mock_db(mapping_entries=[_make_db_entry(provider_id, "admin", nexus_group_id)])

        # "users" is in the token but not in mapping entries
        result = await sync_idp_groups(db, user, identity, {"groups": ["users"]}, config)
        assert result is False
        # Still calls execute for the tracking table query and cleanup
        assert db.exec.call_count > 1

    @pytest.mark.asyncio
    async def test_returns_false_when_claim_missing(self):
        """Should return False when groups claim is absent and mappings are configured."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        config = _make_config(group_jmespath_expression="groups[*]")
        db = _make_mock_db(mapping_entries=[_make_db_entry(provider_id, "admin", nexus_group_id)])

        # No "groups" claim at all
        result = await sync_idp_groups(db, user, identity, {"sub": "user-123"}, config)
        assert result is False
        # Should still execute for tracking table query and cleanup
        assert db.exec.call_count > 1

    @pytest.mark.asyncio
    async def test_handles_scalar_jmespath_result(self):
        """Should wrap scalar JMESPath result into a list."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        config = _make_config(group_jmespath_expression="role")
        db = _make_mock_db(mapping_entries=[_make_db_entry(provider_id, "admin", nexus_group_id)])

        await sync_idp_groups(db, user, identity, {"role": "admin"}, config)
        assert db.exec.call_count > 1

    @pytest.mark.asyncio
    async def test_string_groups_claim_with_wildcard_denied(self):
        """Should deny login when groups claim is a scalar string with [*] expression."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        config = _make_config(group_jmespath_expression="groups[*]")
        db = _make_mock_db(mapping_entries=[_make_db_entry(provider_id, "nexus-users", nexus_group_id)])

        result = await sync_idp_groups(db, user, identity, {"groups": "nexus-users"}, config)
        assert result is False


class TestAllowAllAuthenticated:
    """Tests for the allow_all_authenticated flag."""

    @pytest.mark.asyncio
    async def test_returns_true_with_no_mappings(self):
        """Should return True and add user to users group when allow_all_authenticated is True."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        users_group = _make_builtin_group("users")
        config = _make_config(allow_all_authenticated=True)
        db = _make_mock_db(mapping_entries=[], users_group=users_group)

        result = await sync_idp_groups(db, user, identity, {"groups": ["team-a"]}, config)
        assert result is True

    @pytest.mark.asyncio
    async def test_with_mappings_still_syncs(self):
        """Should sync groups normally AND add users group when allow_all_authenticated is True with mappings."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        users_group = _make_builtin_group("users")
        config = _make_config(group_jmespath_expression="groups[*]", allow_all_authenticated=True)
        db = _make_mock_db(
            mapping_entries=[_make_db_entry(provider_id, "admin", nexus_group_id)],
            users_group=users_group,
        )

        result = await sync_idp_groups(db, user, identity, {"groups": ["admin"]}, config)
        assert result is True
        assert db.exec.call_count > 1

    @pytest.mark.asyncio
    async def test_false_requires_mappings(self):
        """Should return False when allow_all_authenticated is False and no mappings match."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        config = _make_config(allow_all_authenticated=False)
        db = _make_mock_db(mapping_entries=[])

        result = await sync_idp_groups(db, user, identity, {"groups": ["team-a"]}, config)
        assert result is False

    @pytest.mark.asyncio
    async def test_jmespath_failure_still_allows_login(self):
        """Should return True when allow_all_authenticated is True even if JMESPath extraction fails."""
        from unittest.mock import patch

        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        users_group = _make_builtin_group("users")
        config = _make_config(group_jmespath_expression="groups[*]", allow_all_authenticated=True)
        db = _make_mock_db(
            mapping_entries=[_make_db_entry(provider_id, "admin", nexus_group_id)],
            users_group=users_group,
        )

        with patch("syntara.auth.services.idp_group_sync.jmespath.search", side_effect=TypeError("unexpected type")):
            result = await sync_idp_groups(db, user, identity, {"groups": ["admin"]}, config)
        assert result is True

    @pytest.mark.asyncio
    async def test_scalar_claim_mismatch_still_allows_login(self):
        """Should return True when allow_all_authenticated is True even if groups claim is a scalar with [*]."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        users_group = _make_builtin_group("users")
        config = _make_config(group_jmespath_expression="groups[*]", allow_all_authenticated=True)
        db = _make_mock_db(
            mapping_entries=[_make_db_entry(provider_id, "nexus-users", nexus_group_id)],
            users_group=users_group,
        )

        result = await sync_idp_groups(db, user, identity, {"groups": "nexus-users"}, config)
        assert result is True


class TestGroupMappingModels:
    """Tests for group mapping model validation."""

    def test_group_mapping_entry_requires_fields(self):
        entry = OIDCGroupMappingEntry(
            idp_group_value="admin-guid-123",
            nexus_group_id=uuid4(),
        )
        assert entry.idp_group_value == "admin-guid-123"

    def test_oidc_config_with_group_jmespath(self):
        nexus_id = uuid4()
        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="realm_access.roles[*]",
            group_mapping_entries=[OIDCGroupMappingEntry(idp_group_value="admin", nexus_group_id=nexus_id)],
        )
        assert config.group_jmespath_expression == "realm_access.roles[*]"
        assert len(config.group_mapping_entries) == 1

    def test_oidc_config_without_group_jmespath(self):
        config = _make_config()
        assert config.group_jmespath_expression is None
        assert config.group_mapping_entries == []

    def test_oidc_config_serialization_roundtrip(self):
        config = _make_config(group_jmespath_expression="groups[*]")
        data = config.model_dump()
        restored = OIDCConfiguration.model_validate(data)
        assert restored.group_jmespath_expression == "groups[*]"


class TestMatchGroupEntries:
    """Tests for match_group_entries wildcard matching."""

    def test_exact_match(self):
        group_id = uuid4()
        entries = [_make_db_entry(uuid4(), "admins", group_id)]
        result = match_group_entries(entries, {"admins", "users"})
        assert result == {group_id}

    def test_no_match(self):
        entries = [_make_db_entry(uuid4(), "admins", uuid4())]
        result = match_group_entries(entries, {"users", "developers"})
        assert result == set()

    def test_wildcard_star_matches_all(self):
        group_id = uuid4()
        entries = [_make_db_entry(uuid4(), "*", group_id)]
        result = match_group_entries(entries, {"admins", "users", "developers"})
        assert result == {group_id}

    def test_wildcard_prefix(self):
        group_id = uuid4()
        entries = [_make_db_entry(uuid4(), "admin*", group_id)]
        result = match_group_entries(entries, {"admin-prod", "admin-staging", "users"})
        assert result == {group_id}

    def test_wildcard_suffix(self):
        group_id = uuid4()
        entries = [_make_db_entry(uuid4(), "*-leads", group_id)]
        result = match_group_entries(entries, {"team-platform-leads", "team-security-leads", "users"})
        assert result == {group_id}

    def test_wildcard_middle(self):
        group_id = uuid4()
        entries = [_make_db_entry(uuid4(), "org/*/engineers", group_id)]
        result = match_group_entries(entries, {"org/acme/engineers", "org/acme/managers"})
        assert result == {group_id}

    def test_wildcard_no_match(self):
        entries = [_make_db_entry(uuid4(), "admin*", uuid4())]
        result = match_group_entries(entries, {"users", "developers"})
        assert result == set()

    def test_multiple_entries_mixed(self):
        gid1, gid2 = uuid4(), uuid4()
        provider_id = uuid4()
        entries = [
            _make_db_entry(provider_id, "admin*", gid1),
            _make_db_entry(provider_id, "dev-team", gid2),
        ]
        result = match_group_entries(entries, {"admin-prod", "dev-team", "users"})
        assert result == {gid1, gid2}

    def test_wildcard_star_with_empty_group_values(self):
        group_id = uuid4()
        entries = [_make_db_entry(uuid4(), "*", group_id)]
        result = match_group_entries(entries, set())
        assert result == {group_id}

    def test_question_mark_wildcard(self):
        group_id = uuid4()
        entries = [_make_db_entry(uuid4(), "team-?", group_id)]
        result = match_group_entries(entries, {"team-a", "team-b", "team-ab"})
        assert result == {group_id}  # matches team-a and team-b, not team-ab


class TestOIDCIdpType:
    """Tests for idp_type validation on OIDCConfiguration."""

    def test_valid_idp_types(self):
        """All known idp_type values should be accepted."""
        for idp_type in OIDCIdpType:
            config = _make_config()
            config_data = config.model_dump()
            config_data["idp_type"] = idp_type.value
            validated = OIDCConfiguration.model_validate(config_data)
            assert validated.idp_type == idp_type.value

    def test_none_idp_type_accepted(self):
        """idp_type=None should be accepted."""
        config = _make_config()
        assert config.idp_type is None

    def test_unknown_idp_type_rejected(self):
        """Unknown idp_type values should be rejected."""
        with pytest.raises(ValueError, match="Unknown idp_type"):
            OIDCConfiguration(
                provider_type="oidc",
                issuer_url="https://idp.example.com",
                client_id="client-id",
                client_secret="client-secret",
                redirect_uri="http://localhost:8000/callback",
                idp_type="unknown_provider",
            )

    def test_known_idp_type_values(self):
        """OIDCIdpType enum should contain the expected values."""
        assert OIDCIdpType.AAP == "aap"
        assert OIDCIdpType.CUSTOM == "custom"


def _make_builtin_group(name: str) -> MagicMock:
    """Create a mock built-in Group object."""
    group = MagicMock()
    group.id = uuid4()
    group.name = name
    group.is_builtin = True
    return group


def _make_mock_db_for_aap(
    mapping_entries: list[IdpGroupMappingEntry] | None = None,
    builtin_group: MagicMock | None = None,
) -> AsyncMock:
    """Create a mock db session for AAP role mapping tests.

    Call sequence:
    1. IdpGroupMappingEntry query (mapping entries)
    2. Built-in group lookup (_resolve_aap_role_groups)
    3+ Empty results for remaining queries (current_idp_groups, etc.)
    """
    db = AsyncMock()
    entries = mapping_entries or []

    mapping_result = MagicMock()
    mapping_result.all = MagicMock(return_value=entries)

    builtin_result = MagicMock()
    builtin_result.first = MagicMock(return_value=builtin_group)

    def _make_empty_result() -> MagicMock:
        r = MagicMock()
        r.__iter__ = MagicMock(return_value=iter([]))
        r.first = MagicMock(return_value=None)
        r.all = MagicMock(return_value=[])
        return r

    call_count = 0

    async def _exec_side_effect(*args: object, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mapping_result
        if call_count == 2:
            return builtin_result
        return _make_empty_result()

    db.exec = AsyncMock(side_effect=_exec_side_effect)
    return db


class TestAapRoleMapping:
    """Tests for AAP aap_system_role → built-in group mapping."""

    @pytest.mark.asyncio
    async def test_system_administrator_maps_to_admins_group(self):
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        admins_group = _make_builtin_group("admins")
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=admins_group)

        result = await sync_idp_groups(
            db, user, identity, {"iss": "https://idp.example.com/", "aap_system_role": "system_administrator"}, config
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_system_auditor_maps_to_auditors_group(self):
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        auditors_group = _make_builtin_group("auditors")
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=auditors_group)

        result = await sync_idp_groups(
            db, user, identity, {"iss": "https://idp.example.com/", "aap_system_role": "system_auditor"}, config
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_normal_user_maps_to_users_group(self):
        """Normal users are assigned to the built-in users group."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        users_group = _make_builtin_group("users")
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=users_group)

        result = await sync_idp_groups(
            db, user, identity, {"iss": "https://idp.example.com/", "aap_system_role": "normal_user"}, config
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_missing_claim_maps_to_users_group(self):
        """Missing aap_system_role claim means normal user — assigned to the users group."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        users_group = _make_builtin_group("users")
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=users_group)

        result = await sync_idp_groups(
            db, user, identity, {"iss": "https://idp.example.com/", "sub": "user-123"}, config
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_unrecognised_role_maps_to_users_group(self):
        """Unrecognised aap_system_role means normal user — assigned to the users group."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        users_group = _make_builtin_group("users")
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=users_group)

        result = await sync_idp_groups(
            db, user, identity, {"iss": "https://idp.example.com/", "aap_system_role": "some_future_role"}, config
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_non_string_role_maps_to_users_group(self):
        """Non-string aap_system_role (e.g. integer) means normal user, assigned to users group."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        users_group = _make_builtin_group("users")
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=users_group)

        result = await sync_idp_groups(
            db, user, identity, {"iss": "https://idp.example.com/", "aap_system_role": 42}, config
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_normal_user_denied_when_users_group_missing(self):
        """Normal users are denied login if the built-in users group is missing."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=None)

        result = await sync_idp_groups(
            db, user, identity, {"iss": "https://idp.example.com/", "aap_system_role": "normal_user"}, config
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_disabled_flag_skips_mapping(self):
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        config = _make_config(aap_role_mapping_enabled=False, idp_type="aap")
        db = _make_mock_db(mapping_entries=[])

        result = await sync_idp_groups(db, user, identity, {"aap_system_role": "system_administrator"}, config)
        assert result is False

    def test_non_aap_idp_type_rejects_aap_role_mapping(self):
        """Setting aap_role_mapping_enabled on a non-AAP IDP is rejected at validation time."""
        with pytest.raises(ValueError, match="aap_role_mapping_enabled requires idp_type to be 'aap'"):
            _make_config(aap_role_mapping_enabled=True, idp_type="custom")

    @pytest.mark.asyncio
    async def test_aap_mapping_combined_with_claim_based(self):
        """AAP role groups should merge with claim-based mapping groups."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        admins_group = _make_builtin_group("admins")

        entry = _make_db_entry(provider_id, "dev-team", nexus_group_id)
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(mapping_entries=[entry], builtin_group=admins_group)

        result = await sync_idp_groups(
            db,
            user,
            identity,
            {"iss": "https://idp.example.com/", "groups": ["dev-team"], "aap_system_role": "system_administrator"},
            config,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_aap_mapping_proceeds_when_jmespath_fails(self):
        """AAP role mapping should still resolve groups even if JMESPath extraction fails."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        admins_group = _make_builtin_group("admins")

        entry = _make_db_entry(provider_id, "dev-team", nexus_group_id)
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(mapping_entries=[entry], builtin_group=admins_group)

        result = await sync_idp_groups(
            db,
            user,
            identity,
            {"iss": "https://idp.example.com/", "groups": 12345, "aap_system_role": "system_administrator"},
            config,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_builtin_group_not_found_returns_no_match(self):
        """If the built-in group is missing (e.g. soft-deleted), AAP mapping resolves no groups."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=None)

        result = await sync_idp_groups(
            db, user, identity, {"iss": "https://idp.example.com/", "aap_system_role": "system_administrator"}, config
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_issuer_mismatch_rejects_aap_claims(self):
        """AAP role mapping must reject tokens whose iss doesn't match the configured issuer_url."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=_make_builtin_group("admins"))

        result = await sync_idp_groups(
            db,
            user,
            identity,
            {"iss": "https://evil-provider.example.com", "aap_system_role": "system_administrator"},
            config,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_missing_issuer_rejects_aap_claims(self):
        """AAP role mapping must reject tokens with no iss claim."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=_make_builtin_group("admins"))

        result = await sync_idp_groups(db, user, identity, {"aap_system_role": "system_administrator"}, config)
        assert result is False

    @pytest.mark.asyncio
    async def test_issuer_exact_match_with_trailing_slash(self):
        """Issuer comparison uses exact match — iss claim must match stored issuer_url."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        admins_group = _make_builtin_group("admins")
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=admins_group)

        result = await sync_idp_groups(
            db,
            user,
            identity,
            {"iss": "https://idp.example.com/", "aap_system_role": "system_administrator"},
            config,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_issuer_match_without_trailing_slash(self):
        """Issuer comparison tolerates missing trailing slash in the iss claim."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        admins_group = _make_builtin_group("admins")
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        db = _make_mock_db_for_aap(builtin_group=admins_group)

        result = await sync_idp_groups(
            db,
            user,
            identity,
            {"iss": "https://idp.example.com", "aap_system_role": "system_administrator"},
            config,
        )
        assert result is True

    def test_serialization_roundtrip(self):
        config = _make_config(aap_role_mapping_enabled=True, idp_type="aap")
        data = config.model_dump()
        restored = OIDCConfiguration.model_validate(data)
        assert restored.aap_role_mapping_enabled is True
        assert restored.idp_type == "aap"
