"""Plugin Registry behavior."""

from __future__ import annotations

from syntara.execution_plane.registry.stub import StubPluginRegistry
from tests.fixtures.execution_plane import echo_plugin_registry


def test_script_registry_uses_real_manifest_and_declares_no_recipes() -> None:
    registry = StubPluginRegistry()
    manifest = registry.action_manifest("script")

    assert registry.credential_recipe_ids("script") == ()
    assert manifest["metadata"]["name"] == "script-bash"
    assert manifest["spec"]["runtime"]["entryPoint"] == "syntara_node_script:BashScriptStep"


def test_registry_resolves_credential_recipe_ids_from_complete_echo_manifests() -> None:
    registry = echo_plugin_registry()

    assert registry.credential_recipe_ids("echo") == (
        "acme.echo.api-token",
        "acme.echo.workspace-token",
    )
