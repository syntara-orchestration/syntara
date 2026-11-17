"""Temporary Plugin Registry backed by known plugin target manifests."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class PluginRegistryError(Exception):
    """Raised when a Plugin Registry cannot resolve a node type."""


class PluginRegistry(Protocol):
    """Registry interface used to resolve a node type's credential recipes."""

    def credential_recipe_ids(self, node_type: str) -> Sequence[str]:
        """Return reachable credential recipe identifiers in manifest order."""


SCRIPT_BASH_MANIFEST: dict[str, Any] = {
    "apiVersion": "syntara.io/v1alpha1",
    "kind": "Action",
    "metadata": {
        "name": "script-bash",
        "displayName": "Bash Script",
        "description": "Runs Bash code in an isolated subprocess container.",
    },
    "spec": {
        "runtime": {
            "kind": "custom-runner",
            "entryPoint": "syntara_node_script:BashScriptStep",
        },
        "input": {
            "kind": "inline",
            "value": {
                "type": "object",
                "required": ["code"],
                "additionalProperties": False,
                "properties": {
                    "code": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Bash source code to execute.",
                    },
                    "environment": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Environment variables passed to the Bash process.",
                    },
                    "max_output_bytes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1048576,
                        "default": 276480,
                        "description": (
                            "Maximum bytes captured per output stream (1 to 1048576). Output "
                            "beyond this limit is truncated. Defaults to ~270 KB per stream; "
                            "the combined serialized result must not exceed the 1 MiB SDK ABI limit."
                        ),
                    },
                },
            },
        },
        "output": {
            "kind": "inline",
            "value": {
                "type": "object",
                "required": ["return_code", "stdout", "stderr"],
                "additionalProperties": False,
                "properties": {
                    "return_code": {
                        "type": "integer",
                        "description": "Process exit code.",
                    },
                    "stdout": {
                        "type": "string",
                        "description": "Standard output captured from the Bash process.",
                    },
                    "stderr": {
                        "type": "string",
                        "description": "Standard error captured from the Bash process.",
                    },
                },
            },
        },
        "error": {
            "kind": "inline",
            "value": {"type": "object", "additionalProperties": True},
        },
    },
}


class StubPluginRegistry:
    """Temporary Plugin Registry backed by known plugin target manifests."""

    def __init__(self, target_manifests: Mapping[str, Sequence[dict[str, Any]]] | None = None) -> None:
        """Initialize the registry with node types and their target manifests."""
        manifests = {"script": (SCRIPT_BASH_MANIFEST,)} if target_manifests is None else target_manifests
        self._target_manifests = deepcopy(manifests)

    def action_manifest(self, node_type: str) -> dict[str, Any]:
        """Return the Action manifest registered for a workflow node type."""
        manifests = self._target_manifests.get(node_type)
        if manifests is None:
            message = f"No plugin targets are registered for node type {node_type!r}"
            raise PluginRegistryError(message)

        try:
            actions = [manifest for manifest in manifests if manifest.get("kind") == "Action"]
        except (AttributeError, TypeError) as error:
            message = f"Registered plugin targets for node type {node_type!r} are invalid"
            raise PluginRegistryError(message) from error

        if len(actions) != 1:
            message = f"Expected one Action for node type {node_type!r}, found {len(actions)}"
            raise PluginRegistryError(message)
        return deepcopy(actions[0])

    def credential_recipe_ids(self, node_type: str) -> tuple[str, ...]:
        """Return CredentialRecipe IDs reachable from a node Action."""
        manifest = self.action_manifest(node_type)
        target_manifests = self._target_manifests[node_type]
        integration_type_id = _optional_spec_value(manifest, "integrationType")
        if integration_type_id is not None:
            integration_manifest = _find_manifest(target_manifests, "IntegrationType", integration_type_id)
            credential_types = _required_string_sequence(
                _manifest_spec(integration_manifest),
                "credentialTypes",
                f"IntegrationType {integration_type_id!r}",
            )
            recipe_ids = {
                recipe_id
                for recipe_manifest in target_manifests
                if (recipe_manifest.get("kind") == "CredentialRecipe")
                and (recipe_id := _optional_spec_value(recipe_manifest, "id")) is not None
                and recipe_id in credential_types
            }
            missing_recipes = [recipe_id for recipe_id in credential_types if recipe_id not in recipe_ids]
            if missing_recipes:
                message = f"No CredentialRecipe is registered for identifiers {missing_recipes!r}"
                raise PluginRegistryError(message)
            return tuple(credential_types)
        return ()


def _manifest_spec(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a manifest's required specification object."""
    spec = manifest.get("spec")
    if not isinstance(spec, dict):
        message = f"Manifest {manifest.get('metadata', {}).get('name', '<unknown>')!r} has no object spec"
        raise PluginRegistryError(message)
    return spec


def _optional_spec_value(manifest: dict[str, Any], key: str) -> str | None:
    """Return an optional string value from a manifest specification."""
    value = _manifest_spec(manifest).get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        message = f"Manifest spec value {key!r} must be a string"
        raise PluginRegistryError(message)
    return value


def _find_manifest(manifests: Sequence[dict[str, Any]], kind: str, identifier: str) -> dict[str, Any]:
    """Find a target manifest by kind and specification identifier."""
    matches = [
        manifest
        for manifest in manifests
        if manifest.get("kind") == kind and _optional_spec_value(manifest, "id") == identifier
    ]
    if len(matches) != 1:
        message = f"Expected one {kind} with identifier {identifier!r}, found {len(matches)}"
        raise PluginRegistryError(message)
    return matches[0]


def _required_string_sequence(spec: dict[str, Any], key: str, owner: str) -> tuple[str, ...]:
    """Return a required sequence of unique strings from a specification."""
    value = spec.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        message = f"{owner} spec value {key!r} must be a sequence of strings"
        raise PluginRegistryError(message)
    if len(value) != len(set(value)):
        message = f"{owner} spec value {key!r} contains duplicate identifiers"
        raise PluginRegistryError(message)
    return tuple(value)
