"""Queries for the database-backed Execution Plane plugin registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlmodel import col, select

from syntara.execution_plane.registry.models import (
    ExecutionPlaneCredentialRecipe,
    ExecutionPlaneIntegrationType,
    ExecutionPlanePlugin,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.workflow_core.models import NodeType


class PluginContractError(ValueError):
    """Raised when a plugin manifest does not contain a usable schema."""


async def get_execution_plane_plugin(session: AsyncSession, name: str) -> ExecutionPlanePlugin | None:
    """Return the managed plugin record for an Action name, if seeded."""
    result = await session.exec(select(ExecutionPlanePlugin).where(ExecutionPlanePlugin.name == name))
    return result.first()


async def get_execution_plane_plugin_by_node_type(
    session: AsyncSession, node_type: NodeType
) -> ExecutionPlanePlugin | None:
    """Return the managed plugin record for an AO node type, if seeded."""
    result = await session.exec(select(ExecutionPlanePlugin).where(ExecutionPlanePlugin.node_type == node_type))
    return result.first()


def execution_plane_plugin_input_schema(plugin: ExecutionPlanePlugin) -> dict[str, Any]:
    """Return a plugin Action's inline workload input schema."""
    return _inline_schema(plugin.manifest, "input", plugin.name)


def execution_plane_plugin_output_schema(plugin: ExecutionPlanePlugin) -> dict[str, Any]:
    """Return a plugin Action's inline workload output schema."""
    return _inline_schema(plugin.manifest, "output", plugin.name)


def execution_plane_plugin_supports_revision(plugin: ExecutionPlanePlugin, step_revision_id: str) -> bool:
    """Check that a selected compiled revision belongs to this registered Action."""
    document = plugin.resolved_execution
    bindings = document.get("bindings") if isinstance(document, dict) else None
    if not isinstance(bindings, list):
        return False
    return any(
        isinstance(binding, dict)
        and binding.get("step_revision_id") == step_revision_id
        and binding.get("step_identity") == plugin.step_identity
        for binding in bindings
    )


async def execution_plane_plugin_credential_recipe_ids(
    session: AsyncSession, plugin: ExecutionPlanePlugin
) -> tuple[str, ...]:
    """Return CredentialRecipe identifiers reachable from a plugin Action."""
    spec = plugin.manifest.get("spec")
    if not isinstance(spec, dict):
        message = f"Execution Plane plugin {plugin.name!r} manifest has no object spec"
        raise PluginContractError(message)

    integration_type_id = spec.get("integrationType")
    if integration_type_id is None:
        return ()
    if not isinstance(integration_type_id, str):
        message = f"Execution Plane plugin {plugin.name!r} has an invalid IntegrationType identifier"
        raise PluginContractError(message)

    integration_type = (
        await session.exec(
            select(ExecutionPlaneIntegrationType).where(
                ExecutionPlaneIntegrationType.integration_type_id == integration_type_id
            )
        )
    ).first()
    if integration_type is None:
        message = f"No Execution Plane IntegrationType is registered for identifier {integration_type_id!r}"
        raise PluginContractError(message)

    integration_spec = integration_type.manifest.get("spec")
    if not isinstance(integration_spec, dict):
        message = f"Execution Plane IntegrationType {integration_type_id!r} manifest has no object spec"
        raise PluginContractError(message)

    recipe_ids = integration_spec.get("credentialTypes")
    if (
        not isinstance(recipe_ids, list)
        or not all(isinstance(recipe_id, str) for recipe_id in recipe_ids)
        or len(recipe_ids) != len(set(recipe_ids))
    ):
        message = f"Execution Plane IntegrationType {integration_type_id!r} has invalid credential recipe identifiers"
        raise PluginContractError(message)

    recipes = (
        await session.exec(
            select(ExecutionPlaneCredentialRecipe).where(
                ExecutionPlaneCredentialRecipe.integration_type_id == integration_type_id,
                col(ExecutionPlaneCredentialRecipe.credential_recipe_id).in_(recipe_ids),
            )
        )
    ).all()
    registered_recipe_ids = {recipe.credential_recipe_id for recipe in recipes}
    missing_recipe_ids = [recipe_id for recipe_id in recipe_ids if recipe_id not in registered_recipe_ids]
    if missing_recipe_ids:
        message = f"No CredentialRecipe is registered for identifiers {missing_recipe_ids!r}"
        raise PluginContractError(message)
    return tuple(recipe_ids)


def _inline_schema(manifest: dict[str, Any], contract: str, plugin_name: str) -> dict[str, Any]:
    """Extract and validate an inline schema from a canonical Action manifest."""
    spec = manifest.get("spec")
    if not isinstance(spec, dict):
        message = f"Execution Plane plugin {plugin_name!r} manifest has no object spec"
        raise PluginContractError(message)

    contract_value = spec.get(contract)
    if not isinstance(contract_value, dict) or contract_value.get("kind") != "inline":
        message = f"Execution Plane plugin {plugin_name!r} has no inline {contract} schema"
        raise ValueError(message)

    schema = contract_value.get("value")
    if not isinstance(schema, dict):
        message = f"Execution Plane plugin {plugin_name!r} has an invalid inline {contract} schema"
        raise PluginContractError(message)
    return schema
