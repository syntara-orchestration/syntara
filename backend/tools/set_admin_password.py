#!/usr/bin/env python3
"""Set or reset the bootstrap admin user password.

Creates the admin user if it does not exist, or updates the password_hash
if it does.

Usage:
    # Interactive prompt (stdin is a TTY)
    uv run python tools/set_admin_password.py

    # Pipe from a file or command
    cat .secrets/admin-password | uv run python tools/set_admin_password.py
"""

import asyncio
import getpass
import sys
from pathlib import Path
from uuid import uuid4

import structlog
from sqlalchemy import insert
from sqlmodel import select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from syntara.auth.passwords import hash_password
from syntara.authz.seed import (
    BOOTSTRAP_ADMIN_FIRST_NAME,
    BOOTSTRAP_ADMIN_USERNAME,
    try_set_bootstrap_admin_email,
)
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups

logger = structlog.stdlib.get_logger(__name__)

ADMINS_GROUP_NAME = "admins"


async def set_admin_password(password: str) -> None:
    """Create or update the admin user with the given plaintext password."""
    async with AsyncSessionLocal() as session:
        result = await session.exec(
            select(User).where(
                User.username == BOOTSTRAP_ADMIN_USERNAME,
                User.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        admin = result.one_or_none()
        password_hash = hash_password(password)

        if admin is None:
            # Create without email first so a taken placeholder cannot block create.
            admin = User(
                id=uuid4(),
                username=BOOTSTRAP_ADMIN_USERNAME,
                first_name=BOOTSTRAP_ADMIN_FIRST_NAME,
                email=None,
                password_hash=password_hash,
                is_enabled=True,
                is_builtin=True,
            )
            session.add(admin)
            await session.flush()
            await try_set_bootstrap_admin_email(session, admin)
            logger.info("Created admin user", user_id=str(admin.id), email=admin.email)
        else:
            # Password sync must succeed even if placeholder email conflicts.
            admin.password_hash = password_hash
            await session.flush()
            logger.info("Updated admin password", user_id=str(admin.id))
            if admin.email is None:
                await try_set_bootstrap_admin_email(session, admin)

        admin_group = (
            await session.exec(
                select(Group).where(
                    Group.name == ADMINS_GROUP_NAME,
                    Group.deleted_at.is_(None),  # type: ignore[union-attr]
                )
            )
        ).one_or_none()
        if admin_group is not None:
            membership = await session.exec(
                select(user_groups.c.user_id).where(
                    user_groups.c.user_id == admin.id,
                    user_groups.c.group_id == admin_group.id,
                )
            )
            if membership.one_or_none() is None:
                await session.exec(insert(user_groups).values(user_id=admin.id, group_id=admin_group.id))
        else:
            logger.warning("Admins group not found; skipping admin group membership sync")

        await session.commit()
        logger.info("Bootstrap admin password synced", user_id=str(admin.id))


def read_password() -> str:
    """Read password from stdin (prompt if TTY, otherwise read piped input)."""
    if sys.stdin.isatty():
        password = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: passwords do not match", file=sys.stderr)
            sys.exit(1)
        return password
    return sys.stdin.read().strip()


def main() -> int:
    """CLI entry point."""
    password = read_password()
    if not password:
        print("Error: password cannot be empty", file=sys.stderr)
        return 1

    from syntara.auth.passwords import validate_password_complexity

    try:
        validate_password_complexity(password)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    asyncio.run(set_admin_password(password))
    return 0


if __name__ == "__main__":
    sys.exit(main())
