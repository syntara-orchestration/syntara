"""Admin CLI entry point for Syntara administrative operations.

Usage::

    uv run python -m syntara.admin revoke-all-sessions
    uv run python -m syntara.admin revoke-all-sessions --yes

    uv run python -m syntara.admin revoke-user-sessions --username alice
    uv run python -m syntara.admin revoke-user-sessions --username alice --yes

    uv run python -m syntara.admin revoke-idp-sessions --idp-name "Corporate Okta"
    uv run python -m syntara.admin revoke-idp-sessions --idp-name "Corporate Okta" --yes
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import TYPE_CHECKING

from syntara.audit.lifecycle import start_audit_subsystems, stop_audit_subsystems

if TYPE_CHECKING:
    from collections.abc import Callable

import structlog

logger = structlog.stdlib.get_logger(__name__)

_HELP_SKIP_CONFIRM = "Skip confirmation prompt"


def _get_actor() -> str:
    """Return the OS login name of the user running the CLI."""
    try:
        return os.getlogin()
    except OSError:
        return "admin-cli"


def _register_audit_handlers() -> None:
    """Register auth-domain audit handlers with the dispatcher."""
    import syntara.auth.audit  # noqa: PLC0415
    from syntara.audit.discovery import discover_handlers  # noqa: PLC0415
    from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415

    auth_audit_registry = discover_handlers(syntara.auth.audit)
    AuditEventDispatcher.register(auth_audit_registry)


async def _revoke_all_tokens(actor: str) -> None:
    """Set the global revocation timestamp and emit an audit event."""
    _register_audit_handlers()
    start_audit_subsystems()

    from syntara.admin.services import set_global_revocation_timestamp  # noqa: PLC0415
    from syntara.core.database.session import AsyncSessionLocal  # noqa: PLC0415

    async with AsyncSessionLocal() as session:
        now = await set_global_revocation_timestamp(
            session,
            actor_username=actor,
            actor_source="cli",
        )
        await session.commit()

    timestamp_str = now.isoformat()
    logger.info(
        "Global revocation timestamp set",
        timestamp=timestamp_str,
        actor=actor,
    )

    await stop_audit_subsystems()

    print(  # noqa: T201
        f"Global revocation timestamp set to {timestamp_str}\n"
        f"All tokens issued before this time are now invalid.\n"
        f"Actor: {actor}",
    )


async def _revoke_user_sessions(username: str, actor: str) -> None:
    """Revoke all sessions for a specific user."""
    _register_audit_handlers()
    start_audit_subsystems()

    from syntara.admin.services import find_user_by_username, revoke_user_sessions  # noqa: PLC0415
    from syntara.core.database.session import AsyncSessionLocal  # noqa: PLC0415

    async with AsyncSessionLocal() as session:
        user = await find_user_by_username(session, username)

        if not user:
            print(f"ERROR: User '{username}' not found.")  # noqa: T201
            sys.exit(1)

        revoked_count = await revoke_user_sessions(
            session,
            user,
            actor_username=actor,
            actor_source="cli",
        )
        await session.commit()

    logger.info(
        "Revoked all sessions for user",
        username=user.username,
        user_id=str(user.id),
        sessions_revoked=revoked_count,
        actor=actor,
    )

    await stop_audit_subsystems()

    print(  # noqa: T201
        f"Revoked {revoked_count} session(s) for user '{user.username}'.\n"
        f"The user will need to re-authenticate.\n"
        f"Actor: {actor}",
    )


async def _revoke_idp_sessions(idp_name: str, actor: str) -> None:
    """Revoke all sessions authenticated via a specific identity provider."""
    _register_audit_handlers()
    start_audit_subsystems()

    from syntara.admin.services import find_idp_by_name, revoke_idp_sessions  # noqa: PLC0415
    from syntara.core.database.session import AsyncSessionLocal  # noqa: PLC0415

    async with AsyncSessionLocal() as session:
        provider = await find_idp_by_name(session, idp_name)

        if not provider:
            print(f"ERROR: Identity provider '{idp_name}' not found.")  # noqa: T201
            sys.exit(1)

        revoked_count = await revoke_idp_sessions(
            session,
            provider.id,
            idp_name=provider.name,
            actor_username=actor,
            actor_source="cli",
        )
        await session.commit()

    logger.info(
        "Revoked all sessions for identity provider",
        idp_name=provider.name,
        idp_id=str(provider.id),
        sessions_revoked=revoked_count,
        actor=actor,
    )

    await stop_audit_subsystems()

    print(  # noqa: T201
        f"Revoked {revoked_count} session(s) for identity provider '{provider.name}'.\n"
        f"Users who authenticated via this provider will need to re-authenticate.\n"
        f"Actor: {actor}",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m syntara.admin",
        description="Administrative operations.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- revoke-all-sessions ---
    revoke_parser = subparsers.add_parser(
        "revoke-all-sessions",
        help="Invalidate all sessions and tokens issued before the current time",
    )
    revoke_parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help=_HELP_SKIP_CONFIRM,
    )

    # --- revoke-user-sessions ---
    user_parser = subparsers.add_parser(
        "revoke-user-sessions",
        help="Revoke all sessions for a specific user",
    )
    user_parser.add_argument(
        "--username",
        required=True,
        help="Username of the user whose sessions should be revoked",
    )
    user_parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help=_HELP_SKIP_CONFIRM,
    )

    # --- revoke-idp-sessions ---
    idp_parser = subparsers.add_parser(
        "revoke-idp-sessions",
        help="Revoke all sessions authenticated via a specific identity provider",
    )
    idp_parser.add_argument(
        "--idp-name",
        required=True,
        help="Name of the identity provider whose sessions should be revoked",
    )
    idp_parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help=_HELP_SKIP_CONFIRM,
    )

    return parser


def _confirm_or_abort(warning: str, *, skip: bool) -> None:
    """Print a warning and prompt for confirmation; abort on decline."""
    if skip:
        return
    print(warning)  # noqa: T201
    confirmation = input("Continue? [y/N]: ").strip().lower()
    if confirmation != "y":
        print("Aborted.")  # noqa: T201
        sys.exit(0)


def revoke_all_sessions(args: argparse.Namespace) -> None:
    """CLI handler for ``revoke-all-sessions``: confirm then set the global revocation timestamp."""
    _confirm_or_abort(
        "WARNING: This will invalidate ALL active sessions.\nAll users will need to re-authenticate.\n",
        skip=args.yes,
    )
    asyncio.run(_revoke_all_tokens(actor=_get_actor()))


def _run_revoke_user_sessions(args: argparse.Namespace) -> None:
    _confirm_or_abort(
        f"WARNING: This will revoke ALL sessions for user '{args.username}'.\nThe user will need to re-authenticate.\n",
        skip=args.yes,
    )
    asyncio.run(_revoke_user_sessions(username=args.username, actor=_get_actor()))


def _run_revoke_idp_sessions(args: argparse.Namespace) -> None:
    _confirm_or_abort(
        f"WARNING: This will revoke ALL sessions authenticated via '{args.idp_name}'.\n"
        f"Users who authenticated via this provider will need to re-authenticate.\n",
        skip=args.yes,
    )
    asyncio.run(_revoke_idp_sessions(idp_name=args.idp_name, actor=_get_actor()))


_COMMANDS: dict[str, tuple[Callable[[argparse.Namespace], None], str]] = {
    "revoke-all-sessions": (revoke_all_sessions, "Global session revocation failed"),
    "revoke-user-sessions": (_run_revoke_user_sessions, "User session revocation failed"),
    "revoke-idp-sessions": (_run_revoke_idp_sessions, "IdP session revocation failed"),
}


def main() -> None:
    """Parse arguments and execute the admin command."""
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handler, error_msg = _COMMANDS[args.command]
    try:
        handler(args)
    except Exception:
        logger.exception(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
