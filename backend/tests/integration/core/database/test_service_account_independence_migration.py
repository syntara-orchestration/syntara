"""The independent-identity upgrade preserves credentials, grants, and bindings."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from tests.fixtures.database import _get_alembic_config


@pytest.mark.asyncio
async def test_upgrade_preserves_identities(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    password_file = tmp_path / "admin-password"
    password_file.write_text("migration-test-password")
    monkeypatch.setenv("APP_ADMIN_PASSWORD_PATH", str(password_file))
    pg = PostgresContainer("quay.io/sclorg/postgresql-15-c9s")
    for key, value in {
        "POSTGRESQL_USER": pg.username,
        "POSTGRESQL_PASSWORD": pg.password,
        "POSTGRESQL_DATABASE": pg.dbname,
        "POSTGRESQL_ADMIN_PASSWORD": "test-admin",
    }.items():
        pg.with_env(key, value)
    with pg:
        cfg = _get_alembic_config(pg.get_connection_url(driver="asyncpg"))
        await asyncio.to_thread(command.upgrade, cfg, "e7f4a1b2c3d4")
        engine = create_async_engine(pg.get_connection_url(driver="asyncpg"))
        ids = {
            key: uuid4()
            for key in (
                "owner",
                "account",
                "project",
                "other",
                "credential",
                "workflow",
                "trigger",
                "grant",
                "system_grant",
            )
        }
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO principals (id, principal_type) VALUES (:owner, 'user'), (:account, 'service_account')"
                ),
                ids,
            )
            await conn.execute(
                text(
                    "INSERT INTO projects (id, name, is_default) VALUES (:project, 'first', false), (:other, "
                    "'second', false)"
                ),
                ids,
            )
            await conn.execute(
                text(
                    "INSERT INTO service_accounts (id, name, status, project_id, created_by, token_version) "
                    "VALUES (:account, 'shared', 'active', :project, :owner, 7)"
                ),
                ids,
            )
            await conn.execute(
                text(
                    "INSERT INTO service_account_credentials (id, service_account_id, created_by, "
                    "credential_type, identifier, hashed_secret, old_hashed_secret, grace_period_seconds, "
                    "status) VALUES (:credential, :account, :owner, 'client_credentials', 'nx_sa_preserved', "
                    "'current-hash', 'previous-hash', 3600, 'active')"
                ),
                ids,
            )
            await conn.execute(
                text(
                    "INSERT INTO role_assignments (id, principal_id, role_name, project_id, is_builtin) VALUES "
                    "(:grant, :account, 'project-user', :other, false), (:system_grant, :account, 'admin', "
                    "NULL, false)"
                ),
                ids,
            )
            await conn.execute(
                text(
                    "INSERT INTO workflows (id, name, created_by, current_version, is_enabled, project_id) "
                    "VALUES (:workflow, 'bound-workflow', :owner, 1, false, :other)"
                ),
                ids,
            )
            await conn.execute(
                text(
                    "INSERT INTO webhook_triggers (id, webhook_path, workflow_id, trigger_node_id, is_enabled, "
                    "trigger_type) VALUES (:trigger, 'shared-path', :workflow, 'trigger', true, 'eda_trigger')"
                ),
                ids,
            )
            await conn.execute(
                text(
                    "INSERT INTO webhook_trigger_service_accounts (webhook_trigger_id, service_account_id) "
                    "VALUES (:trigger, :account)"
                ),
                ids,
            )
            queries = {
                "service_accounts": text("SELECT * FROM service_accounts"),
                "service_account_credentials": text("SELECT * FROM service_account_credentials"),
                "role_assignments": text("SELECT * FROM role_assignments"),
                "webhook_trigger_service_accounts": text("SELECT * FROM webhook_trigger_service_accounts"),
            }
            before = {table: (await conn.execute(query)).mappings().all() for table, query in queries.items()}
        await asyncio.to_thread(command.upgrade, cfg, "head")
        await engine.dispose()
        async with engine.connect() as conn:
            columns = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_columns("service_accounts"))
            assert next(c for c in columns if c["name"] == "project_id")["nullable"] is True
            foreign_keys = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_foreign_keys("service_accounts")
            )
            project_fk = next(fk for fk in foreign_keys if fk["name"] == "service_accounts_project_id_fkey")
            assert project_fk["options"]["ondelete"] == "SET NULL"
            for table, rows in before.items():
                actual = [dict(row) for row in (await conn.execute(queries[table])).mappings()]
                assert actual == [dict(row) for row in rows]
            await conn.execute(text("DELETE FROM projects WHERE id = :project"), {"project": ids["project"]})
            assert (
                await conn.execute(
                    text("SELECT project_id FROM service_accounts WHERE id = :account"), {"account": ids["account"]}
                )
            ).scalar_one() is None
            for table in ("service_accounts", "service_account_credentials", "role_assignments"):
                assert (await conn.execute(queries[table])).mappings().all()
            await conn.commit()
        with pytest.raises(RuntimeError, match="projectless service accounts"):
            await asyncio.to_thread(command.downgrade, cfg, "e7f4a1b2c3d4")
        await engine.dispose()
