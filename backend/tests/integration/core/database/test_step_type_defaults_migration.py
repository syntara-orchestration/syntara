# Generated with AI assistance: Codex (OpenAI)
"""Exercise the actual data migration on isolated PostgreSQL databases."""

import asyncio
from collections.abc import AsyncGenerator
from importlib import import_module
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy.engine import URL, RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.evaluator import evaluate_policy_input
from syntara.authz.models import Project, RoleAssignment
from syntara.authz.models.role import Role
from syntara.authz.resolver import resolve_effective_policies
from syntara.authz.resource_actions import build_resource_actions
from syntara.authz.role_conventions import BUILTIN_POLICIES, builtin_policy_uuid
from syntara.authz.seed import seed_groups_project_admin
from syntara.authz.services.policy_service import PolicyService
from syntara.authz.services.role_service import RoleService
from syntara.core.models import User
from syntara.core.router_discovery import discover_and_register_routers
from syntara.service_accounts.models.service_account import ServiceAccount
from syntara.workflows.node_kinds import NODE_KINDS
from tests.fixtures.database import _get_alembic_config

MIGRATION = import_module("syntara.core.database.migrations.versions.9e4b7c2a6f81_seed_step_type_authoring_defaults")


@pytest.fixture(scope="module", autouse=True)
def resource_registry() -> None:
    """Register the real API resource catalog without starting external services."""
    app = FastAPI()
    discover_and_register_routers(app=app, prefix="", enable_validation=False)
    build_resource_actions(app)


@pytest_asyncio.fixture
async def migration_db(test_db_admin_url: URL) -> AsyncGenerator[tuple[AsyncEngine, Config], None]:
    """Keep real migration history separate from the shared integration template."""
    url = test_db_admin_url
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    name = f"step_defaults_{uuid4().hex}"
    engine = create_async_engine(url.set(database=name), poolclass=NullPool)
    cfg = _get_alembic_config(engine.url.render_as_string(hide_password=False))
    async with admin.connect() as conn:
        await conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    try:
        await asyncio.to_thread(command.upgrade, cfg, MIGRATION.down_revision)
        yield engine, cfg
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(sa.text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


async def _snapshot(engine: AsyncEngine) -> list[list[RowMapping]]:
    async with engine.connect() as conn:
        return [
            list((await conn.execute(sa.select(table).order_by(table.c.id))).mappings())
            for table in (MIGRATION.POLICIES, MIGRATION.ROLES, MIGRATION.ASSIGNMENTS)
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_group", [False, True])
async def test_install_repeat_and_untouched_downgrade(
    migration_db: tuple[AsyncEngine, Config],
    *,
    existing_group: bool,
) -> None:
    engine, cfg = migration_db
    group_id = uuid4()
    if existing_group:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO groups (id,name,description,is_builtin,source) "
                    "VALUES (:id,'authenticated','operator description',true,'local')"
                ),
                {"id": group_id},
            )
    await asyncio.to_thread(command.upgrade, cfg, "head")
    if existing_group:
        async with engine.connect() as conn:
            row = (await conn.execute(sa.text("SELECT id, description FROM groups WHERE name='authenticated'"))).one()
            assert row == (group_id, "operator description")
    before = await _snapshot(engine)
    assert [len(rows) for rows in before] == [1, 1, 1]
    assert all(not rows[0]["is_builtin"] for rows in before)
    assert before[0][0]["statements"] == MIGRATION.POLICY_DEFAULT["statements"]
    assert before[1][0]["policy_names"] == ["default-step-type-write"]
    assert before[2][0]["project_id"] is None
    assert set(MIGRATION.CATALOG_NAMES) == {p.name for p in BUILTIN_POLICIES if p.effect == "deny"}
    PolicyService._validate_resource_actions(before[0][0]["statements"])
    PolicyService._validate_deny_effect(before[0][0]["statements"])
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert await _snapshot(engine) == before
    await asyncio.to_thread(command.downgrade, cfg, MIGRATION.down_revision)
    assert await _snapshot(engine) == [[], [], []]
    async with engine.connect() as conn:
        assert (await conn.execute(sa.text("SELECT count(*) FROM groups WHERE name='authenticated'"))).scalar_one() == 1
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert [len(rows) for rows in await _snapshot(engine)] == [1, 1, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("table_name", ["POLICIES", "ROLES", "ASSIGNMENTS"])
@pytest.mark.parametrize("change", ["edit", "delete", "touch"])
async def test_admin_changes_survive_restart_and_block_downgrade(
    migration_db: tuple[AsyncEngine, Config],
    table_name: str,
    change: str,
) -> None:
    engine, cfg = migration_db
    await asyncio.to_thread(command.upgrade, cfg, "head")
    table = getattr(MIGRATION, table_name)
    async with engine.begin() as conn:
        if change == "delete":
            stmt = table.delete()
        elif change == "touch":
            stmt = table.update().values(updated_at=sa.func.now())
        else:
            stmt = table.update().values(labels={"admin": "changed"})
        await conn.execute(stmt)
    # Use the normal authz seeder twice, with a password source isolated from the host.
    async with AsyncSession(engine) as session:
        await seed_groups_project_admin(session)
        await seed_groups_project_admin(session)
    before = await _snapshot(engine)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert await _snapshot(engine) == before
    with pytest.raises(RuntimeError, match="edited, deleted, or have additional references"):
        await asyncio.to_thread(command.downgrade, cfg, MIGRATION.down_revision)
    assert await _snapshot(engine) == before
    async with engine.connect() as conn:
        assert (
            await conn.execute(sa.text("SELECT version_num FROM alembic_version"))
        ).scalar_one() == MIGRATION.revision


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["policy", "role", "assignment", "catalog_global", "catalog_project"])
async def test_conflicts_leave_records_and_history_unchanged(
    migration_db: tuple[AsyncEngine, Config],
    conflict: str,
) -> None:
    engine, cfg = migration_db
    async with engine.begin() as conn:
        if conflict == "role":
            await conn.execute(MIGRATION.ROLES.insert().values(**{**MIGRATION.ROLE_DEFAULT, "id": uuid4()}))
        elif conflict == "assignment":
            group_id = uuid4()
            await conn.execute(
                sa.text("INSERT INTO groups (id,name,is_builtin,source) VALUES (:id,'authenticated',true,'local')"),
                {"id": group_id},
            )
            await conn.execute(
                MIGRATION.ASSIGNMENTS.insert().values(**{**MIGRATION.ASSIGNMENT_DEFAULT, "group_id": group_id})
            )
        else:
            values = {**MIGRATION.POLICY_DEFAULT, "id": uuid4()}
            if conflict.startswith("catalog"):
                values["name"] = MIGRATION.CATALOG_NAMES[0]
            if conflict == "catalog_project":
                project = Project(name="existing-project")
                async with AsyncSession(bind=conn) as session:
                    session.add(project)
                    await session.flush()
                values["project_id"] = project.id
            await conn.execute(MIGRATION.POLICIES.insert().values(**values))
    before = await _snapshot(engine)
    with pytest.raises(RuntimeError, match="existing policies="):
        await asyncio.to_thread(command.upgrade, cfg, "head")
    assert await _snapshot(engine) == before
    async with engine.connect() as conn:
        assert (
            await conn.execute(sa.text("SELECT version_num FROM alembic_version"))
        ).scalar_one() == MIGRATION.down_revision


@pytest.mark.asyncio
@pytest.mark.parametrize("reference", ["role", "assignment"])
async def test_extra_references_block_downgrade(migration_db: tuple[AsyncEngine, Config], reference: str) -> None:
    engine, cfg = migration_db
    await asyncio.to_thread(command.upgrade, cfg, "head")
    async with engine.begin() as conn:
        if reference == "role":
            await conn.execute(
                MIGRATION.ROLES.insert().values(**{**MIGRATION.ROLE_DEFAULT, "id": uuid4(), "name": "another-role"})
            )
        else:
            group_id = uuid4()
            await conn.execute(
                sa.text("INSERT INTO groups (id,name,is_builtin,source) VALUES (:id,'another-group',false,'local')"),
                {"id": group_id},
            )
            await conn.execute(
                MIGRATION.ASSIGNMENTS.insert().values(
                    **{**MIGRATION.ASSIGNMENT_DEFAULT, "id": uuid4(), "group_id": group_id}
                )
            )
    before = await _snapshot(engine)
    with pytest.raises(RuntimeError, match="additional references"):
        await asyncio.to_thread(command.downgrade, cfg, MIGRATION.down_revision)
    assert await _snapshot(engine) == before


@pytest.mark.asyncio
async def test_insertion_failure_rolls_back_grants_and_history(migration_db: tuple[AsyncEngine, Config]) -> None:
    engine, cfg = migration_db
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "CREATE FUNCTION reject_seed_role() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'injected role failure'; END $$"
            )
        )
        await conn.execute(
            sa.text(
                "CREATE TRIGGER reject_seed BEFORE INSERT ON roles FOR EACH ROW EXECUTE FUNCTION reject_seed_role()"
            )
        )
    with pytest.raises(sa.exc.DBAPIError, match="injected role failure"):
        await asyncio.to_thread(command.upgrade, cfg, "head")
    assert await _snapshot(engine) == [[], [], []]
    async with engine.connect() as conn:
        assert (await conn.execute(sa.text("SELECT count(*) FROM groups"))).scalar_one() == 0
        assert (
            await conn.execute(sa.text("SELECT version_num FROM alembic_version"))
        ).scalar_one() == MIGRATION.down_revision


@pytest.mark.asyncio
async def test_seeded_grants_and_deny_catalog_resolve_for_principals(migration_db: tuple[AsyncEngine, Config]) -> None:
    engine, cfg = migration_db
    await asyncio.to_thread(command.upgrade, cfg, "head")
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(username="plain-author", email="author@example.com", first_name="Plain", last_name="Author")
        project = Project(name="payments")
        session.add_all([user, project])
        await session.flush()
        service_account = ServiceAccount(name="automation", project_id=project.id, created_by=user.id)
        session.add(service_account)
        await session.commit()
        for principal in (user, service_account):
            effective = await resolve_effective_policies(session, principal.id)
            for kind in NODE_KINDS:
                result = evaluate_policy_input(
                    {
                        "user": {"id": str(principal.id)},
                        "action": "write",
                        "groups": [],
                        "resource": {"type": "step_type", "project": "payments", "labels": {"kind": kind}},
                        "effective_policies": effective,
                    }
                )
                assert result["allow"] is True
            assert not evaluate_policy_input(
                {
                    "user": {"id": str(principal.id)},
                    "action": "create",
                    "groups": [],
                    "resource": {"type": "workflow", "project": "payments"},
                    "effective_policies": effective,
                }
            )["allow"]
        service = PolicyService(session, user)
        assert (await service.get_policy_or_builtin(MIGRATION.POLICY_DEFAULT["id"])).is_builtin is False
        session.add(RoleAssignment(principal_id=user.id, role_name="admin"))
        await session.commit()
        for kind in sorted(NODE_KINDS):
            for scope in ("any", "project"):
                name = f"step_type:write:{scope}:deny:{kind}"
                read = await service.get_policy_or_builtin(builtin_policy_uuid(name))
                assert read.is_builtin is True
                assert read.is_project_eligible is (scope == "project")
                role = Role(
                    name=f"deny-{kind}-{scope}",
                    policy_names=[name],
                    scope="project" if scope == "project" else "system",
                    project_id=project.id if scope == "project" else None,
                )
                await RoleService(session, user)._validate_policy_names([name], role.project_id)
                session.add(role)
                await session.flush()
                assignment = RoleAssignment(principal_id=user.id, role_name=role.name, project_id=role.project_id)
                session.add(assignment)
                await session.commit()
                for context in ("payments", "other"):
                    result = evaluate_policy_input(
                        {
                            "user": {"id": str(user.id)},
                            "action": "write",
                            "groups": [],
                            "resource": {"type": "step_type", "project": context, "labels": {"kind": kind}},
                            "effective_policies": await resolve_effective_policies(session, user.id),
                        }
                    )
                    assert result["deny"] is (scope == "any" or context == "payments")
                    assert result["allow"] is not result["deny"]
                await session.delete(assignment)
                await session.delete(role)
                await session.commit()
        changed = await service.update_policy(
            MIGRATION.POLICY_DEFAULT["id"], name="operator-step-policy", description="Operator customization"
        )
        assert changed.name == "operator-step-policy"
        default_role = await session.get(Role, MIGRATION.ROLE_DEFAULT["id"])
        assert default_role is not None
        assert default_role.policy_names == [changed.name]
        await service.delete_policy(changed.id)
        await seed_groups_project_admin(session)
        await asyncio.to_thread(command.upgrade, cfg, "head")
        assert (await _snapshot(engine))[0] == []
