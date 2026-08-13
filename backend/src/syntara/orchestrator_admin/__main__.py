"""Production admin CLI for account management operations.

Usage::

    orchestrator-admin enable-user --username alice --yes

    orchestrator-admin reset-password --username alice
    orchestrator-admin reset-password --username alice --yes

    # Non-interactive: provide password via flag (visible in process list)
    orchestrator-admin reset-password --username alice --password 'MySecureP@ss1'

    # Non-interactive: provide password via stdin (recommended)
    cat /run/secrets/admin-password | orchestrator-admin reset-password --username alice --password-stdin
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import os
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

import typer

from syntara.audit.lifecycle import start_audit_subsystems, stop_audit_subsystems
from syntara.auth.passwords import validate_password_complexity
from syntara.core.config.base import get_settings as _get_settings

if TYPE_CHECKING:
    from syntara.auth.audit.account_management import AccountEnableEvent, PasswordResetEvent
    from syntara.core.models.user import User

_product_name = _get_settings().product_name

app = typer.Typer(
    name="orchestrator-admin",
    help=f"{_product_name} production administrative operations.",
    no_args_is_help=True,
    add_completion=False,
)


def _quiet_logging() -> None:
    """Suppress INFO/DEBUG log noise while preserving ERROR/CRITICAL output."""
    logging.getLogger().setLevel(logging.ERROR)


def _get_actor() -> str:
    """Return the OS login name of the user running the CLI."""
    try:
        return os.getlogin()
    except OSError:
        return "orchestrator-admin"


def _validate_password(password: str) -> tuple[bool, str | None]:
    """Validate password meets InfoSec security requirements.

    Returns:
        (is_valid, error_message) - error_message is None if valid

    """
    try:
        validate_password_complexity(password)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def _resolve_password(password_flag: str | None, *, password_stdin: bool) -> tuple[str, bool]:
    """Resolve password from --password flag, --password-stdin, or interactive prompt.

    Returns:
        (password, non_interactive) — non_interactive is True when the
        password came from --password or --password-stdin so the
        confirmation prompt should be skipped.

    Raises:
        typer.Exit: If both sources are given, the resolved password is
        empty, or stdin is not a terminal without an explicit source.

    """
    if password_flag is not None and password_stdin:
        typer.echo("ERROR: --password and --password-stdin are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    if password_flag is not None:
        if not password_flag:
            typer.echo("ERROR: --password value must not be empty.", err=True)
            raise typer.Exit(code=1)
        return password_flag, True

    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            typer.echo("ERROR: No password provided via stdin.", err=True)
            raise typer.Exit(code=1)
        return password, True

    if not sys.stdin.isatty():
        typer.echo(
            "ERROR: stdin is not a terminal. Use --password-stdin to read the password from stdin,\n"
            "or --password to supply it as a flag.",
            err=True,
        )
        raise typer.Exit(code=1)

    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        typer.echo("ERROR: Passwords do not match.", err=True)
        raise typer.Exit(code=1)
    return password, False


async def _lookup_local_user(username: str) -> User:
    """Look up a non-deleted user by username. Exits on failure."""
    from sqlmodel import select  # noqa: PLC0415

    from syntara.core.database.session import AsyncSessionLocal  # noqa: PLC0415
    from syntara.core.models import User  # noqa: PLC0415

    async with AsyncSessionLocal() as session:
        result = await session.exec(
            select(User).filter(
                User.username == username.lower(),  # type: ignore[arg-type]
                User.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        user = result.one_or_none()

    if not user:
        typer.echo(f"ERROR: User '{username}' not found.", err=True)
        raise typer.Exit(code=1)

    return user


async def _revoke_sessions_and_dispatch(
    user: User,
    audit_event: AccountEnableEvent | PasswordResetEvent,
) -> None:
    """Revoke all sessions, increment token version, and dispatch an audit event."""
    from syntara.audit.context_managers import actor_context  # noqa: PLC0415
    from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
    from syntara.audit.emitter import AuditActorContext  # noqa: PLC0415
    from syntara.auth.session import create_session_store  # noqa: PLC0415
    from syntara.core.database.session import AsyncSessionLocal  # noqa: PLC0415
    from syntara.core.models.principal import PrincipalType  # noqa: PLC0415

    async with AsyncSessionLocal() as session:
        session.add(user)
        store = create_session_store(session)
        revoked_count = await store.revoke_all_for_user(user.id)
        # CLI has no JWT middleware — attribute token_version CRUD (AAP-83651).
        with actor_context(
            actor=AuditActorContext(
                actor_id=None,
                actor_username=audit_event.actor_username,
                actor_type=PrincipalType.USER,
            )
        ):
            await store.increment_token_version(user.id)
            await session.commit()

    audit_event.sessions_revoked = revoked_count

    try:
        AuditEventDispatcher.dispatch(audit_event)
    except Exception:  # noqa: BLE001
        typer.echo("WARNING: Audit event could not be recorded.", err=True)

    await stop_audit_subsystems()


async def _enable_user_async(username: str, actor: str) -> None:
    """Re-enable a disabled user account."""
    _quiet_logging()
    start_audit_subsystems()

    from syntara.auth.audit.account_management import AccountEnableEvent  # noqa: PLC0415
    from syntara.core.models.user import AuthType  # noqa: PLC0415

    user = await _lookup_local_user(username)

    if user.is_enabled:
        typer.echo(f"User '{user.username}' is already enabled.")
        raise typer.Exit(code=0)

    user.is_enabled = True
    user.updated_at = datetime.now(UTC)

    await _revoke_sessions_and_dispatch(
        user,
        AccountEnableEvent(
            actor_username=actor,
            actor_source="cli",
            target_username=user.username,
            sessions_revoked=0,
        ),
    )

    typer.echo(f"User '{user.username}' has been re-enabled.\nActor: {actor}")
    if user.auth_type == AuthType.LOCAL:
        typer.echo(
            f"\nConsider running 'orchestrator-admin reset-password --username {user.username}' "
            f"if a password reset is also needed."
        )


async def _reset_password_async(username: str, new_password: str, actor: str) -> None:
    """Reset the password for a local user account."""
    _quiet_logging()
    start_audit_subsystems()

    from syntara.auth.audit.account_management import PasswordResetEvent  # noqa: PLC0415
    from syntara.auth.passwords import hash_password  # noqa: PLC0415
    from syntara.core.models.user import AuthType  # noqa: PLC0415

    user = await _lookup_local_user(username)

    if user.auth_type == AuthType.FEDERATED:
        typer.echo(
            f"ERROR: Cannot reset password for identity provider user '{username}'.\n"
            f"This account is managed by an external identity provider and does not have a local password.",
            err=True,
        )
        raise typer.Exit(code=1)

    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now(UTC)

    await _revoke_sessions_and_dispatch(
        user,
        PasswordResetEvent(
            actor_username=actor,
            actor_source="cli",
            target_username=user.username,
            sessions_revoked=0,
        ),
    )

    typer.echo(
        f"Password reset for user '{user.username}'.\n"
        f"All existing sessions have been revoked. "
        f"The user will need to log in with the new password.\n"
        f"Actor: {actor}",
    )


@app.command()
def enable_user(
    username: Annotated[
        str,
        typer.Option(
            "--username",
            "-u",
            help="Username of the account to re-enable (e.g. 'admin' for the built-in admin account)",
        ),
    ],
    yes: Annotated[  # noqa: FBT002
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Re-enable a disabled user account."""
    if not yes:
        typer.confirm(
            f"This will re-enable the disabled account '{username}'.\n"
            f"The user will be able to log in again.\n\n"
            f"Continue?",
            abort=True,
        )
    asyncio.run(_enable_user_async(username=username, actor=_get_actor()))


@app.command()
def reset_password(
    username: Annotated[
        str,
        typer.Option("--username", "-u", help="Username of the account whose password will be reset"),
    ],
    password: Annotated[
        str | None,
        typer.Option(
            "--password",
            "-p",
            help="New password (non-interactive, visible in process list — prefer --password-stdin).",
        ),
    ] = None,
    password_stdin: Annotated[  # noqa: FBT002
        bool,
        typer.Option("--password-stdin", help="Read the new password from stdin."),
    ] = False,
    yes: Annotated[  # noqa: FBT002
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Reset the password for a local user account."""
    resolved_password, non_interactive = _resolve_password(password, password_stdin=password_stdin)

    if not non_interactive and not yes:
        typer.confirm(
            f"This will reset the password for user '{username}'.\n"
            f"The user's current password will be invalidated and all active sessions will be revoked.\n\n"
            f"Continue?",
            abort=True,
        )

    is_valid, error_message = _validate_password(resolved_password)
    if not is_valid:
        typer.echo(f"ERROR: {error_message}", err=True)
        raise typer.Exit(code=1)

    asyncio.run(_reset_password_async(username=username, new_password=resolved_password, actor=_get_actor()))


def main() -> None:
    """Entry point for ``python -m syntara.orchestrator_admin``."""
    app()


if __name__ == "__main__":
    main()
