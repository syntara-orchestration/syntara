"""Dispatch-time conversion of legacy credential references."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def legacy_credential_bindings(credential_ref: str | None, recipe_ids: Sequence[str]) -> list[dict[str, str]]:
    """Convert a legacy single credential reference into an EP binding.

    Existing workflow definitions carry at most one credential reference, while a
    plugin Action can reach multiple credential recipes. A one-to-one conversion
    is only safe when the plugin identifies exactly one recipe.
    """
    if credential_ref is None:
        return []

    recipe_count = len(recipe_ids)
    if recipe_count == 0:
        return []
    if recipe_count > 1:
        message = f"Legacy credential cannot identify one CredentialRecipe from {recipe_count} reachable recipes"
        raise ValueError(message)

    return [
        {
            "credential_recipe_id": recipe_ids[0],
            "credential_ref": credential_ref,
        }
    ]
