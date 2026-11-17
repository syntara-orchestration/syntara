"""Dispatch-time conversion of legacy credential references."""

from __future__ import annotations

from typing import TYPE_CHECKING

from syntara.execution_plane.registry.stub import PluginRegistryError

if TYPE_CHECKING:
    from syntara.execution_plane.registry.stub import PluginRegistry


def legacy_credential_bindings(
    credential_ref: str | None,
    node_type: str,
    registry: PluginRegistry,
) -> list[dict[str, str]]:
    """Convert a legacy single credential reference into an EP binding.

    Existing workflow definitions carry at most one credential reference, while a
    plugin Action can reach multiple credential recipes. A one-to-one conversion
    is only safe when the plugin identifies exactly one recipe.
    """
    if credential_ref is None:
        return []

    recipe_ids = registry.credential_recipe_ids(node_type)
    if len(recipe_ids) == 0:
        return []
    if len(recipe_ids) > 1:
        message = (
            f"Legacy credential for node type {node_type!r} cannot identify one "
            f"CredentialRecipe from {len(recipe_ids)} reachable recipes"
        )
        raise PluginRegistryError(message)

    return [
        {
            "credential_recipe_id": recipe_ids[0],
            "credential_ref": credential_ref,
        }
    ]
