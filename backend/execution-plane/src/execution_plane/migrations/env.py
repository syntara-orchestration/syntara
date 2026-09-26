"""Alembic environment for the execution_plane schema.

Runs migrations scoped to the `execution_plane` PostgreSQL schema only.
The Syntara API's migrations (in backend/src/syntara/core/database/migrations/)
manage the `public` schema independently — these two migration chains never touch
each other's tables.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import Table, pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.schema import SchemaItem

# Import all execution_plane models so they are registered in SQLModel.metadata.
import execution_plane.models.cluster
import execution_plane.models.execution_target
import execution_plane.models.work_item  # noqa: F401

EP_SCHEMA = "execution_plane"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata

database_url = config.get_main_option("sqlalchemy.url") or os.environ.get("DATABASE_URL")
if not database_url:
    msg = "DATABASE_URL must be set or sqlalchemy.url provided in alembic.ini"
    raise RuntimeError(msg)
config.set_main_option("sqlalchemy.url", database_url)


def include_object(
    obj: SchemaItem,
    _name: str | None,
    type_: str,
    _reflected: bool,  # noqa: FBT001 — Alembic passes this callback argument positionally.
    _compare_to: SchemaItem | None,
) -> bool:
    """Restrict autogenerate to the execution_plane schema only."""
    if type_ == "table":
        return isinstance(obj, Table) and obj.schema == EP_SCHEMA
    return True


def run_migrations_offline() -> None:
    """Generate migration SQL without opening a database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        version_table_schema=EP_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run schema-scoped migrations on the supplied connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        version_table_schema=EP_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Connect asynchronously and prepare the execution-plane schema."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {EP_SCHEMA}"))
        await connection.commit()
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
