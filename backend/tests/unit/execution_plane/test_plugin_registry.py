"""Plugin Registry behavior."""

from __future__ import annotations

from syntara.execution_plane.registry.stub import StubPluginRegistry
from tests.fixtures.execution_plane import echo_plugin_registry


def test_script_registry_uses_real_manifest_and_declares_no_recipes() -> None:
    registry = StubPluginRegistry()
    manifest = registry.action_manifest("script")

    assert registry.credential_recipe_ids("script") == ()
    assert registry.step_revision_id("script") == "script.v1"
    assert manifest["metadata"]["name"] == "script-bash"
    assert manifest["spec"]["runtime"]["entryPoint"] == "syntara_node_script:BashScriptStep"


def test_script_registry_exposes_workload_contracts() -> None:
    registry = StubPluginRegistry()

    input_schema = registry.input_schema("script")
    output_schema = registry.output_schema("script")

    assert input_schema["required"] == ["language", "code"]
    assert input_schema["properties"]["language"]["enum"] == ["bash", "python"]
    assert input_schema["properties"]["code"]["minLength"] == 1
    assert input_schema["properties"]["environment"]["additionalProperties"] == {"type": "string"}
    assert output_schema["required"] == ["return_code", "stdout", "stderr"]
    assert output_schema["properties"]["return_code"] == {"type": "integer", "description": "Process exit code."}
    assert output_schema["properties"]["stdout"]["type"] == "string"
    assert output_schema["properties"]["stdout_json"] == {
        "description": "Parsed JSON from stdout (Python scripts only). Present if stdout contains valid JSON.",
    }
    assert output_schema["properties"]["stderr"]["type"] == "string"


def test_registry_resolves_credential_recipe_ids_from_complete_echo_manifests() -> None:
    registry = echo_plugin_registry()

    assert registry.credential_recipe_ids("echo") == (
        "acme.echo.api-token",
        "acme.echo.workspace-token",
    )
