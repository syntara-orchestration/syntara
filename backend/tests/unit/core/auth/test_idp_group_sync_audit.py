"""Tests that IdP group sync emits GroupMembershipEvent (AAP-83643)."""

# ruff: noqa: S106
# mypy: disable-error-code="attr-defined"

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventCategory
from syntara.auth.services.idp_group_sync import sync_idp_groups
from syntara.authz.audit.group_membership import GroupMembershipEvent, GroupMembershipHandler
from syntara.core.models import User, UserIdentity
from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration
from syntara.identity_providers.models.idp_group_mapping import IdpGroupMappingEntry

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent


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


def _make_config() -> OIDCConfiguration:
    return OIDCConfiguration(
        provider_type="oidc",
        issuer_url="https://idp.example.com",
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="http://localhost:8000/callback",
        group_jmespath_expression="groups[*]",
    )


def _make_empty_result() -> MagicMock:
    result = MagicMock()
    result.__iter__ = MagicMock(return_value=iter([]))
    result.all = MagicMock(return_value=[])
    result.first = MagicMock(return_value=None)
    return result


def _make_db(
    mapping_entries: list[IdpGroupMappingEntry],
    *,
    idp_rows: list[tuple[UUID, UUID]] | None = None,
) -> AsyncMock:
    """Mock DB: first exec returns mapping entries; idp-rows query returns *idp_rows* once."""
    db = AsyncMock()
    mapping_result = MagicMock()
    mapping_result.all = MagicMock(return_value=mapping_entries)

    idp_result = MagicMock()
    rows = idp_rows or []
    idp_result.__iter__ = MagicMock(return_value=iter(rows))
    idp_result.all = MagicMock(return_value=rows)

    call_count = 0
    idp_consumed = False

    async def _exec_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
        nonlocal call_count, idp_consumed
        call_count += 1
        if call_count == 1:
            return mapping_result
        if not idp_consumed:
            idp_consumed = True
            return idp_result
        return _make_empty_result()

    db.exec = AsyncMock(side_effect=_exec_side_effect)
    return db


class TestIdpGroupSyncMembershipAudit:
    """IdP-driven membership changes must emit SECURITY_EVENT membership audits."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({GroupMembershipEvent: GroupMembershipHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_matching_group_emits_group_member_added(self, mock_do_emit: AsyncMock) -> None:
        """New IdP-mapped membership must emit group_member_added."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        nexus_group_id = uuid4()
        config = _make_config()
        mapping_entry = IdpGroupMappingEntry(
            id=uuid4(),
            identity_provider_id=provider_id,
            idp_group_value="admin",
            nexus_group_id=nexus_group_id,
        )
        db = _make_db([mapping_entry])

        result = await sync_idp_groups(db, user, identity, {"groups": ["admin"]}, config)

        assert result is True
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]
        assert event.event_action == "group_member_added"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.structured_data.username == "testuser"
        assert event.structured_data.user_id == str(user.id)
        assert event.structured_data.group_id == str(nexus_group_id)

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_stale_idp_membership_emits_group_member_removed(self, mock_do_emit: AsyncMock) -> None:
        """Removing a previous IdP membership must emit group_member_removed."""
        user = _make_user()
        provider_id = uuid4()
        identity = _make_identity(user, provider_id)
        stale_group_id = uuid4()
        config = _make_config()
        mapping_entry = IdpGroupMappingEntry(
            id=uuid4(),
            identity_provider_id=provider_id,
            idp_group_value="admin",
            nexus_group_id=uuid4(),
        )
        db = _make_db([mapping_entry], idp_rows=[(stale_group_id, provider_id)])

        result = await sync_idp_groups(db, user, identity, {"groups": ["unmapped"]}, config)

        assert result is False
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]
        assert event.event_action == "group_member_removed"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.structured_data.username == "testuser"
        assert event.structured_data.group_id == str(stale_group_id)
