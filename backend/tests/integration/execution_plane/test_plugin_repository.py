"""Integration tests for the database-backed Execution Plane plugin registry."""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.execution_plane.registry.models import (
    ExecutionPlaneCredentialRecipe,
    ExecutionPlaneIntegrationType,
    ExecutionPlanePlugin,
)
from syntara.execution_plane.registry.repository import (
    execution_plane_plugin_credential_recipe_ids,
    get_execution_plane_plugin,
    get_execution_plane_plugin_by_node_type,
)
from syntara.workflow_core.models import NodeType
from tests.fixtures.execution_plane import (
    ECHO_ACTION_MANIFEST,
    ECHO_API_TOKEN_RECIPE_MANIFEST,
    ECHO_INTEGRATION_TYPE_MANIFEST,
    ECHO_WORKSPACE_TOKEN_RECIPE_MANIFEST,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_registry_resolves_script_plugins_by_node_type(test_db_session: AsyncSession) -> None:
    """Seeded script Actions are addressable by their AO node type."""
    expected_names = {
        NodeType.SCRIPT_PYTHON: "script-python",
        NodeType.SCRIPT_BASH: "script-bash",
    }

    for node_type, expected_name in expected_names.items():
        plugin = await get_execution_plane_plugin_by_node_type(test_db_session, node_type)
        assert plugin is not None
        assert plugin.name == expected_name


@pytest.mark.asyncio
async def test_registry_resolves_credential_recipe_ids_from_complete_echo_manifests(
    test_db_session: AsyncSession,
) -> None:
    test_db_session.add(
        ExecutionPlanePlugin(
            name="echo",
            node_type=NodeType.HTTP_REQUEST,
            step_identity="acme.echo.echo.v1",
            manifest=ECHO_ACTION_MANIFEST,
            image_reference="quay.io/example/echo:test",
        )
    )
    test_db_session.add(
        ExecutionPlaneIntegrationType(
            integration_type_id="acme.echo.connection",
            manifest=ECHO_INTEGRATION_TYPE_MANIFEST,
        )
    )
    await test_db_session.flush()
    test_db_session.add_all(
        [
            ExecutionPlaneCredentialRecipe(
                credential_recipe_id="acme.echo.api-token",
                integration_type_id="acme.echo.connection",
                manifest=ECHO_API_TOKEN_RECIPE_MANIFEST,
            ),
            ExecutionPlaneCredentialRecipe(
                credential_recipe_id="acme.echo.workspace-token",
                integration_type_id="acme.echo.connection",
                manifest=ECHO_WORKSPACE_TOKEN_RECIPE_MANIFEST,
            ),
        ]
    )
    await test_db_session.commit()

    plugin = await get_execution_plane_plugin(test_db_session, "echo")
    assert plugin is not None
    assert await execution_plane_plugin_credential_recipe_ids(test_db_session, plugin) == (
        "acme.echo.api-token",
        "acme.echo.workspace-token",
    )
