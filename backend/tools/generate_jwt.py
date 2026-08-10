#!/usr/bin/env python3
"""Generate JWT tokens for a user.

This script generates access and refresh tokens for testing and development.
It can create tokens for an existing user or the dev user.

Usage:
    # Generate tokens for the dev user (default)
    uv run tools/generate_jwt.py

    # Generate tokens for a specific user by ID
    uv run tools/generate_jwt.py --user-id 12345678-1234-5678-1234-567812345678

    # Generate tokens for a user by username
    uv run tools/generate_jwt.py --username "dev/admin"

    # Generate only an access token (no refresh token)
    uv run tools/generate_jwt.py --access-only

    # Generate a token with a specific role (overrides the user's actual role)
    uv run tools/generate_jwt.py --role administrator

    # Sign the token with the backup key (for testing key rotation)
    uv run tools/generate_jwt.py --key backup

    # Output as JSON (for scripting)
    uv run tools/generate_jwt.py --json

    # Generate tokens and store refresh token in the database
    uv run tools/generate_jwt.py --store-refresh

Examples:
    # Get tokens for testing API calls
    uv run tools/generate_jwt.py --json | jq -r '.access_token'

    # Use with curl
    TOKEN=$(uv run tools/generate_jwt.py --access-only)
    curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/me

"""

import argparse
import asyncio
import io
import json
import logging
import os
import sys
from uuid import UUID

import structlog
from sqlmodel import select

from syntara.auth.services.token_service import KeyManager, TokenService
from syntara.auth.session import create_session_store
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models import User

# Valid --key choices; paths are resolved at runtime from settings/environment.
_KEY_CHOICES = ("primary", "backup")


async def get_user_by_id(user_id: UUID) -> User | None:
    """Get a user by their ID."""
    async with AsyncSessionLocal() as session:
        result = await session.exec(select(User).filter(User.id == user_id))  # type: ignore[arg-type]
        return result.one_or_none()


async def get_user_by_username(username: str) -> User | None:
    """Get a user by their username."""
    async with AsyncSessionLocal() as session:
        result = await session.exec(select(User).filter(User.username == username))  # type: ignore[arg-type]
        return result.one_or_none()


async def get_admin_user() -> User:
    """Get the admin user."""
    async with AsyncSessionLocal() as session:
        result = await session.exec(select(User).filter(User.username == "admin", User.deleted_at.is_(None)))  # type: ignore[arg-type]
        user = result.first()
        if not user:
            msg = "No admin user found. Run 'uv run python tools/set_admin_password.py' to create one."
            raise SystemExit(msg)
        return user


def _build_key_manager(key_name: str) -> KeyManager:
    """Build a KeyManager that signs with the specified key.

    Resolves key paths from application settings so the script works both
    inside the container and on the host (no hardcoded paths).

    For "primary" the path and key_id come directly from settings.
    For "backup" they are extracted from the ``jwt_backup_keys`` list.

    Args:
        key_name: Key name ("primary" or "backup")

    Returns:
        Configured KeyManager

    Raises:
        SystemExit: If backup key configuration is missing from settings

    """
    settings = get_settings()

    if key_name == "primary":
        # Primary key — just use the default KeyManager (already configured)
        return KeyManager()

    # Backup key — find it in jwt_backup_keys
    backup_keys = settings.jwt_backup_keys or []
    if not backup_keys:
        print("Error: No backup keys configured (APP_JWT_BACKUP_KEYS is empty)", file=sys.stderr)
        sys.exit(1)

    # Use the first backup key entry
    backup_config = backup_keys[0]
    backup_path = backup_config.get("key_path")
    backup_key_id = backup_config.get("key_id")

    if not backup_path or not backup_key_id:
        print(
            "Error: Backup key config must have 'key_path' and 'key_id'",
            file=sys.stderr,
        )
        sys.exit(1)

    # Override env vars so a fresh KeyManager picks up the backup key
    os.environ["APP_JWT_PRIVATE_KEY_PATH"] = backup_path
    os.environ["APP_JWT_KEY_ID"] = backup_key_id
    # Clear settings cache so new env vars take effect
    get_settings.cache_clear()
    return KeyManager()


async def generate_tokens(
    user: User,
    *,
    access_only: bool = False,
    store_refresh: bool = False,
    role_override: str | None = None,
    key_name: str | None = None,
) -> dict[str, str | bool]:
    """Generate tokens for a user.

    Args:
        user: The user to generate tokens for
        access_only: If True, only generate access token
        store_refresh: If True, store refresh token in the database
        role_override: If set, use this role instead of the user's actual role
        key_name: If set, sign with this key ("primary" or "backup")

    Returns:
        Dictionary with token information

    """
    key_manager = _build_key_manager(key_name) if key_name else None
    token_service = TokenService(key_manager=key_manager)

    display_role = role_override or "user"

    # Generate access token
    access_token = token_service.create_access_token(
        user_id=user.id,
        username=user.username,
        email=user.email or "",
    )

    result: dict[str, str | bool] = {
        "user_id": str(user.id),
        "username": user.username,
        "role": display_role,
        "key_id": token_service._key_manager.key_id,  # noqa: SLF001
        "access_token": access_token,
    }

    if not access_only:
        # Generate refresh token
        refresh_token, jti, expires_at = token_service.create_refresh_token(user.id)
        result["refresh_token"] = refresh_token
        result["refresh_token_jti"] = jti
        result["refresh_token_expires_at"] = expires_at.isoformat()

        if store_refresh:
            async with AsyncSessionLocal() as db:
                store = create_session_store(db)
                await store.create(
                    jti=jti,
                    user_id=user.id,
                    device="generate_jwt.py CLI tool",
                )
                await db.commit()
            result["refresh_token_stored"] = True

    return result


def print_tokens(tokens: dict, *, as_json: bool = False) -> None:
    """Print tokens to stdout."""
    if as_json:
        print(json.dumps(tokens, indent=2))
    else:
        print(f"User: {tokens['username']} (ID: {tokens['user_id']})")
        print(f"Role: {tokens['role']}")
        print(f"Key ID: {tokens['key_id']}")
        print()
        print("Access Token:")
        print(tokens["access_token"])

        if "refresh_token" in tokens:
            print()
            print("Refresh Token:")
            print(tokens["refresh_token"])
            print()
            print(f"Refresh Token JTI: {tokens['refresh_token_jti']}")
            print(f"Refresh Token Expires: {tokens['refresh_token_expires_at']}")
            if tokens.get("refresh_token_stored"):
                print("Refresh Token stored in DB: Yes")


async def main() -> int:
    """Run the JWT generation CLI."""
    # When ``--json`` is requested, suppress all log output so that stdout
    # contains only valid JSON.  The Makefile invokes this via
    # ``podman-compose exec -T`` (no TTY) so stderr stays separate, but we
    # still silence logs here as a safeguard.
    # We check for ``--json`` early (before argparse) so that logging is
    # silenced before any syntara code runs.
    # syntara/__init__.py configures structlog with stdlib processors
    # (including filter_by_level) at import time. We must override the full
    # processor chain here, not just the factory, because PrintLogger lacks
    # the .disabled attribute that filter_by_level requires.
    _processors = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
    if "--json" in sys.argv:
        logging.disable(logging.CRITICAL)
        structlog.configure(
            processors=_processors,
            logger_factory=structlog.PrintLoggerFactory(file=io.StringIO()),
        )
    else:
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING, force=True)
        structlog.configure(
            processors=_processors,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        )

    parser = argparse.ArgumentParser(
        description="Generate JWT tokens for a user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--user-id",
        type=str,
        help="UUID of the user to generate tokens for",
    )
    parser.add_argument(
        "--username",
        type=str,
        help="Username of the user to generate tokens for",
    )
    parser.add_argument(
        "--access-only",
        action="store_true",
        help="Generate only an access token (no refresh token)",
    )
    parser.add_argument(
        "--store-refresh",
        action="store_true",
        help="Store the refresh token in Redis (makes it usable for /auth/refresh)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--role",
        type=str,
        choices=["creator", "approver", "administrator", "viewer"],
        help="Override the role embedded in the token (default: user's actual role)",
    )
    parser.add_argument(
        "--key",
        type=str,
        choices=list(_KEY_CHOICES),
        help="Signing key to use (default: primary)",
    )

    args = parser.parse_args()

    # Determine which user to generate tokens for
    user: User | None = None

    if args.user_id:
        try:
            user_uuid = UUID(args.user_id)
        except ValueError:
            print(f"Error: Invalid UUID format: {args.user_id}", file=sys.stderr)
            return 1

        user = await get_user_by_id(user_uuid)
        if not user:
            print(f"Error: User not found with ID: {args.user_id}", file=sys.stderr)
            return 1

    elif args.username:
        user = await get_user_by_username(args.username)
        if not user:
            print(f"Error: User not found with username: {args.username}", file=sys.stderr)
            return 1

    else:
        # Use dev user
        user = await get_admin_user()

    # Generate tokens
    tokens = await generate_tokens(
        user,
        access_only=args.access_only,
        store_refresh=args.store_refresh,
        role_override=args.role,
        key_name=args.key,
    )

    # Output
    print_tokens(tokens, as_json=args.json)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
