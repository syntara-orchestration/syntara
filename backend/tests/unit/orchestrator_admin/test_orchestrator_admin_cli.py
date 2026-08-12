"""Unit tests for the orchestrator-admin CLI enable-user and reset-password commands."""

import re
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import typer

from syntara.core.models.user import AuthType
from syntara.orchestrator_admin.__main__ import (
    _enable_user_async,
    _get_actor,
    _reset_password_async,
    _resolve_password,
    _validate_password,
)


def _make_mock_user(
    username: str = "alice",
    *,
    auth_type: AuthType = AuthType.LOCAL,
    is_enabled: bool = True,
) -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.username = username
    user.auth_type = auth_type
    user.is_enabled = is_enabled
    return user


def _mock_session_returning(entity: MagicMock | None) -> AsyncMock:
    """Build a mock AsyncSessionLocal that returns `entity` from a SELECT query."""
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = entity

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    return mock_session


def _session_factory(mock_session: AsyncMock) -> AsyncMock:
    return AsyncMock(
        __aenter__=AsyncMock(return_value=mock_session),
        __aexit__=AsyncMock(return_value=False),
    )


# ---------------------------------------------------------------------------
# _validate_password
# ---------------------------------------------------------------------------


class TestValidatePassword:
    """Tests for _validate_password helper (InfoSec requirements)."""

    def test_rejects_password_under_14_characters(self) -> None:
        """Should reject passwords with fewer than 14 characters."""
        is_valid, error = _validate_password("Short123!")
        assert is_valid is False
        assert error is not None
        assert "at least 14 characters" in error

    def test_rejects_password_with_only_lowercase(self) -> None:
        """Should reject passwords with only 1 character class."""
        is_valid, error = _validate_password("lowercasepasswordonly")  # 21 chars, 1 class
        assert is_valid is False
        assert error is not None
        assert "at least 3 of the following character classes" in error

    def test_rejects_password_with_only_two_classes(self) -> None:
        """Should reject passwords with only 2 character classes."""
        is_valid, error = _validate_password("lowercaseonly123456")  # lowercase + digits
        assert is_valid is False
        assert error is not None
        assert "at least 3 of the following character classes" in error

    def test_accepts_password_with_upper_lower_digit(self) -> None:
        """Should accept passwords with 3 classes: uppercase + lowercase + digits."""
        is_valid, error = _validate_password("ValidPassword123")
        assert is_valid is True
        assert error is None

    def test_accepts_password_with_lower_digit_special(self) -> None:
        """Should accept passwords with 3 classes: lowercase + digits + special."""
        is_valid, error = _validate_password("validpassword123!@#")
        assert is_valid is True
        assert error is None

    def test_accepts_password_with_upper_digit_special(self) -> None:
        """Should accept passwords with 3 classes: uppercase + digits + special."""
        is_valid, error = _validate_password("VALIDPASSWORD123!")
        assert is_valid is True
        assert error is None

    def test_accepts_password_with_upper_lower_special(self) -> None:
        """Should accept passwords with 3 classes: uppercase + lowercase + special."""
        is_valid, error = _validate_password("ValidPassword!@#$")
        assert is_valid is True
        assert error is None

    def test_accepts_password_with_all_four_classes(self) -> None:
        """Should accept passwords with all 4 character classes."""
        is_valid, error = _validate_password("ValidPassword123!")
        assert is_valid is True
        assert error is None

    def test_accepts_password_with_spaces(self) -> None:
        """Should accept passwords containing spaces (counts as special characters)."""
        is_valid, error = _validate_password("Valid Password 123")
        assert is_valid is True
        assert error is None

    def test_accepts_exactly_14_chars_with_three_classes(self) -> None:
        """Should accept minimum length boundary: exactly 14 characters with 3 classes."""
        is_valid, error = _validate_password("ValidPass123!!")
        assert is_valid is True
        assert error is None


# ---------------------------------------------------------------------------
# _get_actor
# ---------------------------------------------------------------------------


class TestGetActor:
    """Tests for _get_actor helper."""

    def test_returns_os_login(self) -> None:
        with patch("syntara.orchestrator_admin.__main__.os.getlogin", return_value="jdoe"):
            assert _get_actor() == "jdoe"

    def test_falls_back_on_os_error(self) -> None:
        with patch("syntara.orchestrator_admin.__main__.os.getlogin", side_effect=OSError("no tty")):
            assert _get_actor() == "orchestrator-admin"


# ---------------------------------------------------------------------------
# enable-user
# ---------------------------------------------------------------------------


class TestEnableUser:
    """Tests for the enable-user CLI command."""

    @pytest.mark.asyncio
    async def test_enables_disabled_local_user(self) -> None:
        """Should set is_enabled=True, revoke sessions, and dispatch audit event."""
        mock_user = _make_mock_user(is_enabled=False)
        mock_session = _mock_session_returning(mock_user)

        mock_store = MagicMock()
        mock_store.revoke_all_for_user = AsyncMock(return_value=2)
        mock_store.increment_token_version = AsyncMock()

        with (
            patch("syntara.orchestrator_admin.__main__.start_audit_subsystems"),
            patch("syntara.orchestrator_admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=_session_factory(mock_session),
            ),
            patch("syntara.auth.session.create_session_store", return_value=mock_store),
            patch("syntara.audit.dispatcher.AuditEventDispatcher") as mock_dispatcher,
        ):
            await _enable_user_async(username="alice", actor="orchestrator-admin")

        assert mock_user.is_enabled is True
        mock_store.revoke_all_for_user.assert_called_once_with(mock_user.id)
        mock_store.increment_token_version.assert_called_once_with(mock_user.id)
        mock_dispatcher.dispatch.assert_called_once()

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.target_username == mock_user.username
        assert event.actor_username == "orchestrator-admin"
        assert event.sessions_revoked == 2

    @pytest.mark.asyncio
    async def test_enables_disabled_idp_user(self) -> None:
        """Should re-enable identity provider users (they just can't have passwords reset)."""
        mock_user = _make_mock_user(auth_type=AuthType.FEDERATED, is_enabled=False)
        mock_session = _mock_session_returning(mock_user)

        mock_store = MagicMock()
        mock_store.revoke_all_for_user = AsyncMock(return_value=0)
        mock_store.increment_token_version = AsyncMock()

        with (
            patch("syntara.orchestrator_admin.__main__.start_audit_subsystems"),
            patch("syntara.orchestrator_admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=_session_factory(mock_session),
            ),
            patch("syntara.auth.session.create_session_store", return_value=mock_store),
            patch("syntara.audit.dispatcher.AuditEventDispatcher") as mock_dispatcher,
        ):
            await _enable_user_async(username="alice", actor="orchestrator-admin")

        assert mock_user.is_enabled is True
        mock_dispatcher.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_exits_with_error_for_unknown_user(self) -> None:
        """Should raise typer.Exit(1) when user is not found."""
        mock_session = _mock_session_returning(None)

        with (
            patch("syntara.orchestrator_admin.__main__.start_audit_subsystems"),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=_session_factory(mock_session),
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            await _enable_user_async(username="nonexistent", actor="orchestrator-admin")

        assert exc_info.value.exit_code == 1

    @pytest.mark.asyncio
    async def test_exits_cleanly_for_already_enabled_user(self) -> None:
        """Should raise typer.Exit(0) when user is already enabled."""
        mock_user = _make_mock_user(is_enabled=True)
        mock_session = _mock_session_returning(mock_user)

        with (
            patch("syntara.orchestrator_admin.__main__.start_audit_subsystems"),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=_session_factory(mock_session),
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            await _enable_user_async(username="alice", actor="orchestrator-admin")

        assert exc_info.value.exit_code == 0

    @pytest.mark.asyncio
    async def test_custom_actor_recorded(self) -> None:
        """Should use the custom actor name in the audit event."""
        mock_user = _make_mock_user(is_enabled=False)
        mock_session = _mock_session_returning(mock_user)

        mock_store = MagicMock()
        mock_store.revoke_all_for_user = AsyncMock(return_value=0)
        mock_store.increment_token_version = AsyncMock()

        with (
            patch("syntara.orchestrator_admin.__main__.start_audit_subsystems"),
            patch("syntara.orchestrator_admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=_session_factory(mock_session),
            ),
            patch("syntara.auth.session.create_session_store", return_value=mock_store),
            patch("syntara.audit.dispatcher.AuditEventDispatcher") as mock_dispatcher,
        ):
            await _enable_user_async(username="alice", actor="security-team@corp.com")

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.actor_username == "security-team@corp.com"


# ---------------------------------------------------------------------------
# reset-password
# ---------------------------------------------------------------------------


class TestResetPassword:
    """Tests for the reset-password CLI command."""

    @pytest.mark.asyncio
    async def test_resets_password_for_local_user(self) -> None:
        """Should update password_hash, revoke sessions, and dispatch audit event."""
        mock_user = _make_mock_user()
        mock_session = _mock_session_returning(mock_user)

        mock_store = MagicMock()
        mock_store.revoke_all_for_user = AsyncMock(return_value=3)
        mock_store.increment_token_version = AsyncMock()

        with (
            patch("syntara.orchestrator_admin.__main__.start_audit_subsystems"),
            patch("syntara.orchestrator_admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=_session_factory(mock_session),
            ),
            patch("syntara.auth.session.create_session_store", return_value=mock_store),
            patch("syntara.auth.passwords.hash_password", return_value="$argon2id$hashed") as mock_hash,
            patch("syntara.audit.dispatcher.AuditEventDispatcher") as mock_dispatcher,
        ):
            await _reset_password_async(username="alice", new_password="newpassword123", actor="orchestrator-admin")  # noqa: S106

        mock_hash.assert_called_once_with("newpassword123")
        assert mock_user.password_hash == "$argon2id$hashed"  # noqa: S105
        mock_store.revoke_all_for_user.assert_called_once_with(mock_user.id)
        mock_store.increment_token_version.assert_called_once_with(mock_user.id)
        mock_dispatcher.dispatch.assert_called_once()

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.target_username == mock_user.username
        assert event.actor_username == "orchestrator-admin"
        assert event.sessions_revoked == 3

    @pytest.mark.asyncio
    async def test_exits_with_error_for_unknown_user(self) -> None:
        """Should raise typer.Exit(1) when user is not found."""
        mock_session = _mock_session_returning(None)

        with (
            patch("syntara.orchestrator_admin.__main__.start_audit_subsystems"),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=_session_factory(mock_session),
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            await _reset_password_async(
                username="nonexistent",
                new_password="newpassword123",  # noqa: S106
                actor="orchestrator-admin",
            )

        assert exc_info.value.exit_code == 1

    @pytest.mark.asyncio
    async def test_exits_with_error_for_idp_user(self) -> None:
        """Should raise typer.Exit(1) for identity provider users."""
        mock_user = _make_mock_user(auth_type=AuthType.FEDERATED)
        mock_session = _mock_session_returning(mock_user)

        with (
            patch("syntara.orchestrator_admin.__main__.start_audit_subsystems"),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=_session_factory(mock_session),
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            await _reset_password_async(username="alice", new_password="newpassword123", actor="orchestrator-admin")  # noqa: S106

        assert exc_info.value.exit_code == 1

    @pytest.mark.asyncio
    async def test_custom_actor_recorded(self) -> None:
        """Should use the custom actor name in the audit event."""
        mock_user = _make_mock_user()
        mock_session = _mock_session_returning(mock_user)

        mock_store = MagicMock()
        mock_store.revoke_all_for_user = AsyncMock(return_value=0)
        mock_store.increment_token_version = AsyncMock()

        with (
            patch("syntara.orchestrator_admin.__main__.start_audit_subsystems"),
            patch("syntara.orchestrator_admin.__main__.stop_audit_subsystems", new_callable=AsyncMock),
            patch(
                "syntara.core.database.session.AsyncSessionLocal",
                return_value=_session_factory(mock_session),
            ),
            patch("syntara.auth.session.create_session_store", return_value=mock_store),
            patch("syntara.auth.passwords.hash_password", return_value="$argon2id$hashed"),
            patch("syntara.audit.dispatcher.AuditEventDispatcher") as mock_dispatcher,
        ):
            await _reset_password_async(username="alice", new_password="newpassword123", actor="ops@example.com")  # noqa: S106

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.actor_username == "ops@example.com"


# ---------------------------------------------------------------------------
# _resolve_password
# ---------------------------------------------------------------------------


class TestResolvePassword:
    """Tests for _resolve_password helper (flag / stdin / interactive precedence)."""

    def test_returns_password_from_flag(self) -> None:
        """--password flag should be returned directly with non_interactive=True."""
        password, non_interactive = _resolve_password("MySecureP@ss1", password_stdin=False)
        assert password == "MySecureP@ss1"  # noqa: S105
        assert non_interactive is True

    def test_exits_when_flag_is_empty_string(self) -> None:
        """--password '' should exit with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            _resolve_password("", password_stdin=False)
        assert exc_info.value.exit_code == 1

    def test_exits_when_both_password_and_stdin_given(self) -> None:
        """--password and --password-stdin together should exit with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            _resolve_password("SomeValue", password_stdin=True)
        assert exc_info.value.exit_code == 1

    def test_reads_password_from_stdin_when_flag_set(self) -> None:
        """--password-stdin should read one line from stdin."""
        fake_stdin = StringIO("PipedPassword123!\n")
        with patch("syntara.orchestrator_admin.__main__.sys.stdin", fake_stdin):
            password, non_interactive = _resolve_password(None, password_stdin=True)
        assert password == "PipedPassword123!"  # noqa: S105
        assert non_interactive is True

    def test_strips_only_trailing_newline_from_stdin(self) -> None:
        """Should strip trailing newline but preserve spaces in the password."""
        fake_stdin = StringIO("My Password 123!\n")
        with patch("syntara.orchestrator_admin.__main__.sys.stdin", fake_stdin):
            password, _ = _resolve_password(None, password_stdin=True)
        assert password == "My Password 123!"  # noqa: S105

    def test_exits_when_password_stdin_is_empty(self) -> None:
        """Should exit with code 1 when --password-stdin gets empty input."""
        fake_stdin = StringIO("")
        with (
            patch("syntara.orchestrator_admin.__main__.sys.stdin", fake_stdin),
            pytest.raises(typer.Exit) as exc_info,
        ):
            _resolve_password(None, password_stdin=True)
        assert exc_info.value.exit_code == 1

    def test_exits_when_password_stdin_is_only_newline(self) -> None:
        """Should exit with code 1 when --password-stdin gets only a newline."""
        fake_stdin = StringIO("\n")
        with (
            patch("syntara.orchestrator_admin.__main__.sys.stdin", fake_stdin),
            pytest.raises(typer.Exit) as exc_info,
        ):
            _resolve_password(None, password_stdin=True)
        assert exc_info.value.exit_code == 1

    def test_exits_when_non_tty_without_explicit_source(self) -> None:
        """Should exit with code 1 when stdin is not a TTY and neither flag is given."""
        fake_stdin = StringIO("some piped data\n")
        with (
            patch("syntara.orchestrator_admin.__main__.sys.stdin", fake_stdin),
            pytest.raises(typer.Exit) as exc_info,
        ):
            _resolve_password(None, password_stdin=False)
        assert exc_info.value.exit_code == 1

    def test_interactive_prompt_when_tty(self) -> None:
        """Should use getpass when stdin is a TTY and no flag is provided."""
        with (
            patch("syntara.orchestrator_admin.__main__.sys.stdin") as mock_stdin,
            patch(
                "syntara.orchestrator_admin.__main__.getpass.getpass", side_effect=["MyPassword123!", "MyPassword123!"]
            ),
        ):
            mock_stdin.isatty.return_value = True
            password, non_interactive = _resolve_password(None, password_stdin=False)
        assert password == "MyPassword123!"  # noqa: S105
        assert non_interactive is False

    def test_interactive_prompt_exits_on_mismatch(self) -> None:
        """Should exit with code 1 when interactive passwords don't match."""
        with (
            patch("syntara.orchestrator_admin.__main__.sys.stdin") as mock_stdin,
            patch("syntara.orchestrator_admin.__main__.getpass.getpass", side_effect=["password1", "password2"]),
            pytest.raises(typer.Exit) as exc_info,
        ):
            mock_stdin.isatty.return_value = True
            _resolve_password(None, password_stdin=False)
        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# reset-password CLI integration (non-interactive modes)
# ---------------------------------------------------------------------------


class TestResetPasswordNonInteractive:
    """Tests for reset-password command with --password flag and stdin."""

    def test_password_flag_skips_confirmation_and_prompts(self) -> None:
        """--password flag should bypass both confirmation and getpass prompts."""
        from typer.testing import CliRunner

        from syntara.orchestrator_admin.__main__ import app

        runner = CliRunner()
        with (
            patch("syntara.orchestrator_admin.__main__._validate_password", return_value=(True, None)),
            patch("syntara.orchestrator_admin.__main__.asyncio.run") as mock_run,
        ):
            result = runner.invoke(app, ["reset-password", "--username", "alice", "--password", "ValidPassword123!"])

        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_password_flag_still_validates(self) -> None:
        """--password flag should still enforce password validation."""
        from typer.testing import CliRunner

        from syntara.orchestrator_admin.__main__ import app

        runner = CliRunner()
        with patch("syntara.orchestrator_admin.__main__._resolve_password", return_value=("short", True)):
            result = runner.invoke(app, ["reset-password", "--username", "alice", "--password", "short"])

        assert result.exit_code == 1

    def test_password_stdin_flag_through_cli(self) -> None:
        """--password-stdin should flow through CliRunner without mocking _resolve_password."""
        from typer.testing import CliRunner

        from syntara.orchestrator_admin.__main__ import app

        runner = CliRunner()
        with (
            patch("syntara.orchestrator_admin.__main__._validate_password", return_value=(True, None)),
            patch("syntara.orchestrator_admin.__main__.asyncio.run") as mock_run,
        ):
            result = runner.invoke(
                app,
                ["reset-password", "--username", "alice", "--password-stdin"],
                input="PipedPassword123!\n",
            )

        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_password_stdin_empty_through_cli(self) -> None:
        """Empty stdin with --password-stdin should fail through CliRunner."""
        from typer.testing import CliRunner

        from syntara.orchestrator_admin.__main__ import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["reset-password", "--username", "alice", "--password-stdin"],
            input="",
        )

        assert result.exit_code == 1
        assert "No password provided via stdin" in result.output

    def test_password_stdin_invalid_password_through_cli(self) -> None:
        """Invalid password via --password-stdin should fail validation through CliRunner."""
        from typer.testing import CliRunner

        from syntara.orchestrator_admin.__main__ import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["reset-password", "--username", "alice", "--password-stdin"],
            input="short\n",
        )

        assert result.exit_code == 1
        assert "at least 14 characters" in result.output

    def test_non_tty_without_flag_fails_through_cli(self) -> None:
        """Piped stdin without --password-stdin should fail through CliRunner."""
        from typer.testing import CliRunner

        from syntara.orchestrator_admin.__main__ import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["reset-password", "--username", "alice"],
            input="PipedPassword123!\n",
        )

        assert result.exit_code == 1
        assert "--password-stdin" in result.output

    def test_password_and_password_stdin_mutually_exclusive(self) -> None:
        """--password and --password-stdin together should fail."""
        from typer.testing import CliRunner

        from syntara.orchestrator_admin.__main__ import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["reset-password", "--username", "alice", "--password", "X", "--password-stdin"],
            input="Y\n",
        )

        assert result.exit_code == 1
        assert "mutually exclusive" in result.output

    def test_help_shows_password_options(self) -> None:
        """--password and --password-stdin should appear in the help output."""
        from typer.testing import CliRunner

        from syntara.orchestrator_admin.__main__ import app

        runner = CliRunner()
        result = runner.invoke(app, ["reset-password", "--help"])
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert result.exit_code == 0
        assert "--password-stdin" in plain
        assert "--password" in plain.split("--password-stdin")[0]


# ---------------------------------------------------------------------------
# Typer CLI integration
# ---------------------------------------------------------------------------


class TestTyperCommands:
    """Tests for Typer command registration and help output."""

    def test_help_lists_commands(self) -> None:
        from typer.testing import CliRunner

        from syntara.orchestrator_admin.__main__ import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert result.exit_code == 0
        assert "enable-user" in plain
        assert "reset-password" in plain
