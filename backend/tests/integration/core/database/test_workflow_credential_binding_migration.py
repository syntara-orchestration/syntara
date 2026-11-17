"""Integration tests for workflow credential-binding JSONB migration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy

from syntara.execution_plane.database.migrations import (
    downgrade_workflow_credential_bindings,
    migrate_workflow_credential_bindings,
)
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.fixtures.execution_plane import echo_plugin_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


def _definition(node_type: str, credential_id: str | None = None) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "code": "printf 'hello'",
        "environment": {"EXAMPLE": "value"},
    }
    if credential_id is not None:
        parameters["credential_id"] = credential_id
    return {
        "id": "workflow",
        "name": "Workflow",
        "nodes": [{"id": "node", "type": node_type, "parameters": parameters}],
        "edges": [],
    }


async def _create_version(
    session: AsyncSession,
    user: User,
    project_id: UUID,
    definition: dict[str, Any],
) -> UUID:
    suffix = uuid4().hex[:8]
    workflow = Workflow(
        name=f"credential-migration-{suffix}",
        created_by=user.id,
        updated_by=user.id,
        current_version=1,
        is_enabled=False,
        project_id=project_id,
    )
    session.add(workflow)
    await session.flush()
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=definition,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(version)
    await session.flush()
    return version.id


async def _definition_by_id(engine: AsyncEngine, version_id: UUID) -> dict[str, Any]:
    async with engine.connect() as connection:
        result = await connection.execute(
            sqlalchemy.text("SELECT workflow_definition FROM workflow_versions WHERE id = :id").bindparams(
                id=version_id
            )
        )
    definition = result.scalar_one()
    assert isinstance(definition, dict)
    return definition


@pytest.mark.asyncio
async def test_workflow_credential_binding_migration_is_idempotent(
    test_db_session: AsyncSession,
    test_db_engine: AsyncEngine,
    test_user: User,
    test_project_id: UUID,
) -> None:
    credential_id = str(uuid4())
    script_version_id = await _create_version(
        test_db_session, test_user, test_project_id, _definition("script", credential_id)
    )
    unchanged_version_id = await _create_version(test_db_session, test_user, test_project_id, _definition("script"))
    echo_version_id = await _create_version(
        test_db_session, test_user, test_project_id, _definition("echo", credential_id)
    )
    await test_db_session.commit()

    async with test_db_engine.connect() as connection:
        await connection.run_sync(migrate_workflow_credential_bindings)
        await connection.commit()

    script_definition = await _definition_by_id(test_db_engine, script_version_id)
    unchanged_definition = await _definition_by_id(test_db_engine, unchanged_version_id)
    echo_definition = await _definition_by_id(test_db_engine, echo_version_id)

    script_parameters = script_definition["nodes"][0]["parameters"]
    unchanged_parameters = unchanged_definition["nodes"][0]["parameters"]
    echo_parameters = echo_definition["nodes"][0]["parameters"]
    assert isinstance(script_parameters, dict)
    assert isinstance(unchanged_parameters, dict)
    assert isinstance(echo_parameters, dict)
    assert "credential_id" not in script_parameters
    assert "credential_bindings" not in script_parameters
    assert "credential_id" not in unchanged_parameters
    assert "credential_bindings" not in unchanged_parameters
    assert "credential_id" in echo_parameters

    async with test_db_engine.connect() as connection:
        await connection.run_sync(
            migrate_workflow_credential_bindings,
            node_types=("echo",),
            registry=echo_plugin_registry(),
        )
        await connection.commit()

    migrated_echo_definition = await _definition_by_id(test_db_engine, echo_version_id)
    migrated_echo_parameters = migrated_echo_definition["nodes"][0]["parameters"]
    assert isinstance(migrated_echo_parameters, dict)
    assert migrated_echo_parameters["credential_bindings"] == [
        {"credential_recipe_id": "acme.echo.api-token", "credential_ref": credential_id},
        {"credential_recipe_id": "acme.echo.workspace-token", "credential_ref": credential_id},
    ]
    assert "credential_id" not in migrated_echo_parameters

    async with test_db_engine.connect() as connection:
        await connection.run_sync(
            migrate_workflow_credential_bindings,
            node_types=("echo",),
            registry=echo_plugin_registry(),
        )
        await connection.commit()

    assert await _definition_by_id(test_db_engine, echo_version_id) == migrated_echo_definition

    async with test_db_engine.connect() as connection:
        await connection.run_sync(
            downgrade_workflow_credential_bindings,
            node_types=("echo",),
        )
        await connection.commit()

    downgraded_echo_definition = await _definition_by_id(test_db_engine, echo_version_id)
    downgraded_echo_parameters = downgraded_echo_definition["nodes"][0]["parameters"]
    assert isinstance(downgraded_echo_parameters, dict)
    assert downgraded_echo_parameters["credential_id"] == credential_id
    assert "credential_bindings" not in downgraded_echo_parameters
