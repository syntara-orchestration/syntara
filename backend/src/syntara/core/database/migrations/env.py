"""Alembic environment configuration for async migrations."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from syntara.core.config.base import get_settings
from syntara.core.database.migrations.models import ALL_MODELS  # noqa: F401
from syntara.core.database.ssl import build_ssl_connect_args
from syntara.core.logging.logging import configure_app_logging

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# disable_existing_loggers=False so running a migration does not disable
# application loggers that were already created (e.g. "syntara.audit.otel"),
# matching the project-wide logging convention in core.logging.logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Set target metadata from models
target_metadata = SQLModel.metadata


# Use the same database URL from centralized settings unless overridden.
config.set_main_option(
    "sqlalchemy.url",
    config.get_main_option("sqlalchemy.url") or get_settings().database_url.render_as_string(hide_password=False),
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    configure_app_logging()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    settings = get_settings()
    ssl_connect_args = build_ssl_connect_args(
        ssl_mode=settings.db_ssl_mode,
        ssl_root_cert=settings.db_ssl_root_cert,
        ssl_cert=settings.db_ssl_cert,
        ssl_key=settings.db_ssl_key,
    )
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=ssl_connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
