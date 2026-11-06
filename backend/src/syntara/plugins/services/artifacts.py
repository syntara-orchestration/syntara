"""Shared helpers for reading Syntara plugin artifacts from a registry.

The media types and artifact layout consumed here are defined by the
``syntara-plugin-sdk``. Both catalog synchronization and plugin installation
use these helpers so verification rules stay in one place.
"""

import gzip
import json
import tarfile
from io import BytesIO
from typing import Any

from syntara.plugins.exceptions import PluginRegistryValidationError
from syntara.plugins.services.oci_client import (
    OciRegistryClient,
    descriptor_digest,
    descriptor_media_type,
    find_layer_by_media_type,
)

CATALOG_INDEX_ARTIFACT_TYPE = "application/vnd.syntara.catalog-index.v1"
CATALOG_CONFIG_MEDIA_TYPE = "application/vnd.syntara.catalog-index.config.v1+json"
CATALOG_CONTENT_MEDIA_TYPE = "application/vnd.syntara.catalog-index.content.v1+json"
PLUGIN_ARTIFACT_TYPE = "application/vnd.syntara.plugin.v1"
PLUGIN_CONFIG_MEDIA_TYPE = "application/vnd.syntara.plugin.config.v1+json"
PLUGIN_MANIFEST_MEDIA_TYPE = "application/vnd.syntara.plugin.manifest.v1+yaml"
PLUGIN_CONTENT_MEDIA_TYPE = "application/vnd.syntara.plugin.content.v1.tar+gzip"


def parse_json(content: bytes, what: str) -> dict[str, Any]:
    """Parse JSON bytes into a mapping, raising a registry validation error."""
    try:
        document = json.loads(content)
    except (ValueError, UnicodeDecodeError) as error:
        msg = f"{what} is not valid JSON"
        raise PluginRegistryValidationError(msg) from error
    if not isinstance(document, dict):
        msg = f"{what} is not a JSON object"
        raise PluginRegistryValidationError(msg)
    return document


def summarize_targets(descriptor: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract action and trigger summaries from a plugin descriptor."""
    actions: list[dict[str, Any]] = []
    triggers: list[dict[str, Any]] = []
    spec = descriptor.get("spec", {}) if isinstance(descriptor.get("spec"), dict) else {}
    targets = spec.get("targets", [])
    if not isinstance(targets, list):
        return actions, triggers
    workloads = spec.get("workloads", {})
    if not isinstance(workloads, dict):
        workloads = {}
    for target in targets:
        if not isinstance(target, dict):
            continue
        metadata = target.get("metadata", {}) if isinstance(target.get("metadata"), dict) else {}
        runtime = target.get("runtime", {}) if isinstance(target.get("runtime"), dict) else {}
        operation = runtime.get("operation", {}) if isinstance(runtime.get("operation"), dict) else {}
        # Custom-runner targets reference a logical workload image ID; the
        # compiled descriptor maps it to the digest-pinned image reference.
        workload_id = runtime.get("workload")
        workload_binding = (
            workloads.get(workload_id, {})
            if isinstance(workload_id, str) and isinstance(workloads.get(workload_id), dict)
            else {}
        )
        summary = {
            "identity": target.get("identity"),
            "name": metadata.get("name"),
            "display_name": metadata.get("displayName"),
            "description": metadata.get("description"),
            "runtime_kind": runtime.get("kind"),
            "driver": runtime.get("driver"),
            "method": operation.get("method"),
            "path": operation.get("path"),
            "implementation": runtime.get("implementation"),
            "implementation_source": runtime.get("implementation_source"),
            "entry_point": runtime.get("entryPoint"),
            "abi": runtime.get("abi") or workload_binding.get("abi"),
            "workload": workload_id,
            "workload_image": workload_binding.get("image"),
            "input_schema": target.get("input"),
        }
        if target.get("kind") == "Trigger":
            triggers.append(summary)
        else:
            actions.append(summary)
    return actions, triggers


def documentation_path(descriptor: dict[str, Any]) -> str | None:
    """Return the documentation path declared by a plugin descriptor."""
    spec = descriptor.get("spec")
    documentation = spec.get("documentation") if isinstance(spec, dict) else None
    if not isinstance(documentation, dict):
        return None
    path = documentation.get("path")
    return path if isinstance(path, str) and path else None


def extract_file(content_bundle: bytes, path: str) -> bytes | None:
    """Read one file out of a plugin content bundle (in-memory tar.gz).

    The bundle is a deterministic tar.gz of asset files (see the SDK artifact
    builder). Extraction never touches the filesystem.
    """
    try:
        with (
            gzip.GzipFile(fileobj=BytesIO(content_bundle)) as decompressed,
            tarfile.open(fileobj=decompressed, mode="r:tar") as archive,  # type: ignore[call-overload]
        ):
            for member in archive.getmembers():
                if member.name == path and member.isfile():
                    extracted = archive.extractfile(member)
                    return extracted.read() if extracted else None
    except (OSError, tarfile.TarError) as error:
        msg = f"plugin content bundle could not be read: {error}"
        raise PluginRegistryValidationError(msg) from error
    return None


async def read_plugin_artifact(
    client: OciRegistryClient, repository: str, manifest: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    """Fetch and verify the descriptor and content bundle of a plugin artifact."""
    config_descriptor = manifest.get("config")
    if not isinstance(config_descriptor, dict):
        msg = "plugin manifest is missing its config"
        raise PluginRegistryValidationError(msg)
    if descriptor_media_type(config_descriptor) != PLUGIN_CONFIG_MEDIA_TYPE:
        msg = "plugin manifest config has an unexpected media type"
        raise PluginRegistryValidationError(msg)
    await client.get_blob(repository, descriptor_digest(config_descriptor))

    manifest_layer = find_layer_by_media_type(manifest, PLUGIN_MANIFEST_MEDIA_TYPE)
    if manifest_layer is None:
        msg = "plugin manifest has no plugin.manifest.yaml layer"
        raise PluginRegistryValidationError(msg)
    descriptor_content = await client.get_blob(repository, descriptor_digest(manifest_layer))
    descriptor = parse_json(descriptor_content, "plugin descriptor")

    content_layer = find_layer_by_media_type(manifest, PLUGIN_CONTENT_MEDIA_TYPE)
    if content_layer is None:
        msg = "plugin manifest has no content.tar.gz layer"
        raise PluginRegistryValidationError(msg)
    content_bundle = await client.get_blob(repository, descriptor_digest(content_layer))
    return descriptor, content_bundle
