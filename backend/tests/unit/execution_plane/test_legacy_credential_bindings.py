"""Dispatch-time conversion of legacy credential references."""

from __future__ import annotations

from uuid import uuid4

import pytest

from syntara.execution_plane.registry.bindings import legacy_credential_bindings
from syntara.execution_plane.registry.stub import PluginRegistryError, StubPluginRegistry


class FakePluginRegistry:
    """Registry double for future plugin node types."""

    def __init__(self, recipe_ids: tuple[str, ...]) -> None:
        """Store the recipes reachable from the future plugin."""
        self.recipe_ids = recipe_ids

    def credential_recipe_ids(self, node_type: str) -> tuple[str, ...]:
        assert node_type == "future-plugin"
        return self.recipe_ids


def test_returns_no_binding_without_a_legacy_credential() -> None:
    assert legacy_credential_bindings(None, "future-plugin", StubPluginRegistry()) == []


def test_returns_no_binding_when_plugin_declares_no_recipe() -> None:
    credential_ref = str(uuid4())

    result = legacy_credential_bindings(credential_ref, "future-plugin", FakePluginRegistry(()))

    assert result == []


def test_maps_single_legacy_credential_to_plugin_recipe() -> None:
    credential_ref = str(uuid4())

    result = legacy_credential_bindings(
        credential_ref,
        "future-plugin",
        FakePluginRegistry(("future.plugin.token",)),
    )

    assert result == [
        {
            "credential_recipe_id": "future.plugin.token",
            "credential_ref": credential_ref,
        }
    ]


def test_rejects_ambiguous_legacy_credential_for_multiple_recipes() -> None:
    credential_ref = str(uuid4())

    with pytest.raises(PluginRegistryError, match="cannot identify one CredentialRecipe"):
        legacy_credential_bindings(
            credential_ref,
            "future-plugin",
            FakePluginRegistry(("future.plugin.token", "future.plugin.workspace")),
        )
