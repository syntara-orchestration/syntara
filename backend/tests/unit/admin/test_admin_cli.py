"""Unit tests for the admin CLI revoke-all-sessions, revoke-user-sessions, and revoke-idp-sessions commands."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.admin.__main__ import _get_actor, _revoke_all_tokens, _revoke_idp_sessions, _revoke_user_sessions


def _make_mock_user(username: str = "alice") -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.username = username
    return user


def _make_mock_provider(name: str = "Corporate Okta") -> MagicMock:
    provider = MagicMock()
    provider.id = uuid4()
    provider.name = name
    return provider


# ---------------------------------------------------------------------------
# revoke-all-sessions
# ---------------------------------------------------------------------------


def _mock_db_session(*, rowcount: int = 1) -> AsyncMock:
    """Build a mock AsyncSessionLocal context with configurable rowcount."""
    mock_execute_result = MagicMock()
    mock_execute_result.rowcount = rowcount

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_execute_result)
    mock_session.commit = AsyncMock()
    return mock_session


class TestRevokeAllTokens:
    """Tests for the revoke-all-sessions CLI command."""

    @pytest.mark.asyncio
    async def test_sets_global_revocation_timestamp(self) -> None:
        """Should call set_global_revocation_timestamp and commit."""
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        mock_session = _mock_db_session(rowcount=1)

        with (
            patch("syntara.admin.__main__._register_audit_handlers"),
            patch("syntara.admin.__main__.start_audit_subsystems"),
            patch("syntara.admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch(
                "syntara.admin.services.set_global_revocation_timestamp",
                new_callable=AsyncMock,
                return_value=now,
            ) as mock_set,
        ):
            await _revoke_all_tokens(actor="admin-cli")

        mock_set.assert_called_once_with(mock_session, actor_username="admin-cli", actor_source="cli")
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_inserts_singleton_when_no_row_exists(self) -> None:
        """Should delegate to set_global_revocation_timestamp which handles upsert."""
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        mock_session = _mock_db_session(rowcount=0)

        with (
            patch("syntara.admin.__main__._register_audit_handlers"),
            patch("syntara.admin.__main__.start_audit_subsystems"),
            patch("syntara.admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch(
                "syntara.admin.services.set_global_revocation_timestamp",
                new_callable=AsyncMock,
                return_value=now,
            ) as mock_set,
        ):
            await _revoke_all_tokens(actor="admin-cli")

        mock_set.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_actor_recorded(self) -> None:
        """Should pass the custom actor name to set_global_revocation_timestamp."""
        from datetime import UTC, datetime

        mock_session = _mock_db_session(rowcount=1)

        with (
            patch("syntara.admin.__main__._register_audit_handlers"),
            patch("syntara.admin.__main__.start_audit_subsystems"),
            patch("syntara.admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch(
                "syntara.admin.services.set_global_revocation_timestamp",
                new_callable=AsyncMock,
                return_value=datetime.now(UTC),
            ) as mock_set,
        ):
            await _revoke_all_tokens(actor="security-team@corp.com")

        mock_set.assert_called_once_with(mock_session, actor_username="security-team@corp.com", actor_source="cli")


# ---------------------------------------------------------------------------
# revoke-user-sessions
# ---------------------------------------------------------------------------


class TestRevokeUserSessions:
    """Tests for the revoke-user-sessions CLI command."""

    @pytest.mark.asyncio
    async def test_revokes_sessions_for_valid_user(self) -> None:
        """Should revoke all sessions and increment token version for a valid user."""
        mock_user = _make_mock_user()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_user

        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(return_value=mock_result)

        mock_store = MagicMock()
        mock_store.revoke_all_for_user = AsyncMock(return_value=3)
        mock_store.increment_token_version = AsyncMock()

        with (
            patch("syntara.admin.__main__._register_audit_handlers"),
            patch("syntara.admin.__main__.start_audit_subsystems"),
            patch("syntara.admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch("syntara.admin.services.create_session_store", return_value=mock_store),
            patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher,
        ):
            await _revoke_user_sessions(username="alice", actor="admin-cli")

        mock_store.revoke_all_for_user.assert_called_once_with(mock_user.id)
        mock_store.increment_token_version.assert_called_once_with(mock_user.id)
        mock_dispatcher.dispatch.assert_called_once()

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.target_type == "user"
        assert event.target_identifier == mock_user.username
        assert event.sessions_revoked == 3
        assert event.actor_username == "admin-cli"

    @pytest.mark.asyncio
    async def test_exits_with_error_for_unknown_user(self) -> None:
        """Should exit with code 1 when user is not found."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(return_value=mock_result)

        with (
            patch("syntara.admin.__main__._register_audit_handlers"),
            patch("syntara.admin.__main__.start_audit_subsystems"),
            patch("syntara.admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            pytest.raises(SystemExit, match="1"),
        ):
            await _revoke_user_sessions(username="nonexistent", actor="admin-cli")

    @pytest.mark.asyncio
    async def test_custom_actor_recorded(self) -> None:
        """Should use the custom actor name in the audit event."""
        mock_user = _make_mock_user()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_user

        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(return_value=mock_result)

        mock_store = MagicMock()
        mock_store.revoke_all_for_user = AsyncMock(return_value=0)
        mock_store.increment_token_version = AsyncMock()

        with (
            patch("syntara.admin.__main__._register_audit_handlers"),
            patch("syntara.admin.__main__.start_audit_subsystems"),
            patch("syntara.admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch("syntara.admin.services.create_session_store", return_value=mock_store),
            patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher,
        ):
            await _revoke_user_sessions(username="alice", actor="security-team@corp.com")

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.actor_username == "security-team@corp.com"


# ---------------------------------------------------------------------------
# revoke-idp-sessions
# ---------------------------------------------------------------------------


class TestRevokeIdpSessions:
    """Tests for the revoke-idp-sessions CLI command."""

    @pytest.mark.asyncio
    async def test_revokes_sessions_for_valid_idp(self) -> None:
        """Should revoke all sessions for a valid identity provider."""
        mock_provider = _make_mock_provider()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_provider

        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(return_value=mock_result)

        mock_store = MagicMock()
        mock_store.revoke_by_idp = AsyncMock(return_value=5)

        with (
            patch("syntara.admin.__main__._register_audit_handlers"),
            patch("syntara.admin.__main__.start_audit_subsystems"),
            patch("syntara.admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch("syntara.admin.services.create_session_store", return_value=mock_store),
            patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher,
        ):
            await _revoke_idp_sessions(idp_name="Corporate Okta", actor="admin-cli")

        mock_store.revoke_by_idp.assert_called_once_with(str(mock_provider.id))
        mock_dispatcher.dispatch.assert_called_once()

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.target_type == "idp"
        assert event.target_identifier == mock_provider.name
        assert event.sessions_revoked == 5
        assert event.actor_username == "admin-cli"

    @pytest.mark.asyncio
    async def test_exits_with_error_for_unknown_idp(self) -> None:
        """Should exit with code 1 when identity provider is not found."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(return_value=mock_result)

        with (
            patch("syntara.admin.__main__._register_audit_handlers"),
            patch("syntara.admin.__main__.start_audit_subsystems"),
            patch("syntara.admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            pytest.raises(SystemExit, match="1"),
        ):
            await _revoke_idp_sessions(idp_name="Nonexistent Provider", actor="admin-cli")

    @pytest.mark.asyncio
    async def test_custom_actor_recorded(self) -> None:
        """Should use the custom actor name in the audit event."""
        mock_provider = _make_mock_provider()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_provider

        mock_session = AsyncMock()
        mock_session.exec = AsyncMock(return_value=mock_result)

        mock_store = MagicMock()
        mock_store.revoke_by_idp = AsyncMock(return_value=0)

        with (
            patch("syntara.admin.__main__._register_audit_handlers"),
            patch("syntara.admin.__main__.start_audit_subsystems"),
            patch("syntara.admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch("syntara.admin.services.create_session_store", return_value=mock_store),
            patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher,
        ):
            await _revoke_idp_sessions(idp_name="Corporate Okta", actor="ops@example.com")

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.actor_username == "ops@example.com"


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


class TestGetActor:
    """Tests for _get_actor helper."""

    def test_returns_os_login(self) -> None:
        """Should return the OS login name."""
        with patch("syntara.admin.__main__.os.getlogin", return_value="jdoe"):
            assert _get_actor() == "jdoe"

    def test_falls_back_on_os_error(self) -> None:
        """Should fall back to 'admin-cli' when os.getlogin() raises OSError."""
        with patch("syntara.admin.__main__.os.getlogin", side_effect=OSError("no tty")):
            assert _get_actor() == "admin-cli"


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_revoke_user_sessions_requires_username(self) -> None:
        """The --username flag should be required for revoke-user-sessions."""
        from syntara.admin.__main__ import _build_parser

        parser = _build_parser()
        with pytest.raises(SystemExit, match="2"):
            parser.parse_args(["revoke-user-sessions"])

    def test_revoke_user_sessions_parses_all_flags(self) -> None:
        """Should parse --username and --yes."""
        from syntara.admin.__main__ import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["revoke-user-sessions", "--username", "alice", "--yes"])

        assert args.command == "revoke-user-sessions"
        assert args.username == "alice"
        assert args.yes is True

    def test_revoke_idp_sessions_requires_idp_name(self) -> None:
        """The --idp-name flag should be required for revoke-idp-sessions."""
        from syntara.admin.__main__ import _build_parser

        parser = _build_parser()
        with pytest.raises(SystemExit, match="2"):
            parser.parse_args(["revoke-idp-sessions"])

    def test_revoke_idp_sessions_parses_all_flags(self) -> None:
        """Should parse --idp-name and --yes."""
        from syntara.admin.__main__ import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["revoke-idp-sessions", "--idp-name", "Corporate Okta", "--yes"])

        assert args.command == "revoke-idp-sessions"
        assert args.idp_name == "Corporate Okta"
        assert args.yes is True

    def test_revoke_user_sessions_defaults(self) -> None:
        """Should default --yes to False."""
        from syntara.admin.__main__ import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["revoke-user-sessions", "--username", "bob"])

        assert args.yes is False

    def test_revoke_idp_sessions_defaults(self) -> None:
        """Should default --yes to False."""
        from syntara.admin.__main__ import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["revoke-idp-sessions", "--idp-name", "Keycloak"])

        assert args.yes is False

    def test_revoke_all_sessions_parses_all_flags(self) -> None:
        """Should parse --yes for revoke-all-sessions."""
        from syntara.admin.__main__ import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["revoke-all-sessions", "--yes"])

        assert args.command == "revoke-all-sessions"
        assert args.yes is True

    def test_revoke_all_sessions_defaults(self) -> None:
        """Should default --yes to False."""
        from syntara.admin.__main__ import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["revoke-all-sessions"])

        assert args.yes is False
