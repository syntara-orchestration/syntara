"""Bundle all domain OpenAPI sub-specs into a single merged openapi.yaml.

Reads each domain sub-spec under src/syntara/schemas/*/openapi.yaml (and
*.openapi.yaml variants), resolves all $ref pointers, merges paths and
components, and writes a self-contained YAML document with no external refs.

Usage:
    uv run python tools/bundle_openapi.py
    uv run python tools/bundle_openapi.py -o path/to/output.yaml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from syntara.api.constants import API_V1_VERSION

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = PROJECT_ROOT / "src" / "syntara" / "schemas"
DEFAULT_OUTPUT = SCHEMAS_DIR / "openapi.yaml"

# Base shared-schemas file whose component schemas are merged into the bundled
# output as named entries (instead of being inlined at every usage site).
_BASE_SHARED_SCHEMAS_FILE = SCHEMAS_DIR / "base" / "shared-resources.openapi.yaml"

# Sub-spec discovery: folders under schemas/ that contain REST OpenAPI files.
# Folders in this set are skipped during discovery.
_SKIP_DIRS = {
    "base",  # shared base schemas, not a domain spec
}

# Files to skip even if they look like OpenAPI specs.
_SKIP_FILES = {
    "shared-schemas.yaml",
    "shared-resources.openapi.yaml",
    "workflow-websocket-api.yaml",
}

# Shared schemas that are abstract base types not exposed directly by the API.
# These are excluded from the bundled output: they won't appear as named
# components, and any external $ref to them will be inlined at usage sites.
_EXCLUDED_FROM_BUNDLE_OUTPUT: frozenset[str] = frozenset(
    {
        "BaseResource",
        "NamedResource",
        "SoftDeletableResource",
        "UserOwnedResource",
        "Resource",
        "ResourcesResponseBase",
    }
)

# ---------------------------------------------------------------------------
# $ref resolution
# ---------------------------------------------------------------------------

_file_cache: dict[Path, dict[str, Any]] = {}


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and cache a YAML file."""
    if path not in _file_cache:
        _file_cache[path] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _file_cache[path]


def _resolve_json_pointer(data: Any, pointer: str) -> Any:
    """Traverse data using a JSON Pointer (RFC 6901) string like '/components/schemas/Foo'."""
    if not pointer or pointer == "/":
        return data
    parts = pointer.lstrip("/").split("/")
    node = data
    for part in parts:
        part_parsed = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if part_parsed not in node:
                raise KeyError(f"JSON Pointer segment '{part_parsed}' not found")
            node = node[part_parsed]
        elif isinstance(node, list):
            node = node[int(part_parsed)]
        else:
            raise TypeError(f"Cannot traverse into {type(node)} with key '{part_parsed}'")
    return node


def _circular_ref_error(ref: str, source_file: Path | None = None) -> ValueError:
    location = f" (in {source_file})" if source_file else ""
    return ValueError(f"Circular $ref detected: {ref}{location}. OpenAPI specs must not contain circular references.")


def _resolve_external_ref(
    file_part: str,
    fragment: str,
    ref: str,
    base_path: Path,
    visited: set[str],
    shared_refs: dict[str, str],
) -> Any:
    """Resolve an external file $ref and return the inlined (or shared-ref) result."""
    target_file = (base_path / file_part).resolve()
    visit_key = f"{target_file}#{fragment}"
    if visit_key in shared_refs:
        return {"$ref": shared_refs[visit_key]}
    if visit_key in visited:
        raise _circular_ref_error(ref, base_path)
    target_data = _load_yaml(target_file)

    # Register the external file's own component schemas so that same-file
    # $refs within it (e.g. #/components/schemas/ActivityStatus inside
    # shared-schemas.yaml) are preserved as named component refs instead of
    # being inlined at every usage site.
    # Excluded schemas are intentionally omitted so that refs to them within
    # inlined schemas are themselves inlined (not kept as dangling local refs).
    extended_shared_refs = dict(shared_refs)
    for section, items in target_data.get("components", {}).items():
        if isinstance(items, dict):
            for name in items:
                if section == "schemas" and name in _EXCLUDED_FROM_BUNDLE_OUTPUT:
                    continue
                key = f"{target_file}#/components/{section}/{name}"
                if key not in extended_shared_refs:
                    extended_shared_refs[key] = f"#/components/{section}/{name}"

    resolved = _resolve_json_pointer(target_data, fragment) if fragment else target_data
    return _resolve_refs(
        resolved,
        target_file.parent,
        visited | {visit_key},
        root_doc=target_data,
        shared_refs=extended_shared_refs,
        current_file=target_file,
    )


def _resolve_same_file_ref(
    fragment: str,
    ref: str,
    base_path: Path,
    visited: set[str],
    root_doc: Any,
    shared_refs: dict[str, str],
    current_file: Path | None,
) -> Any:
    """Resolve a same-file ``#/…`` $ref and return the inlined (or shared-ref) result."""
    if not fragment:
        # Bare "#" — refers to the whole document; preserve as-is.
        return {"$ref": ref}
    if current_file is not None:
        self_visit_key = f"{current_file}#{fragment}"
        if self_visit_key in shared_refs:
            return {"$ref": shared_refs[self_visit_key]}
    visit_key = f"<self>#{fragment}"
    if visit_key in visited:
        raise _circular_ref_error(ref, base_path)
    try:
        target = _resolve_json_pointer(root_doc, fragment)
    except (KeyError, TypeError, ValueError):
        # Pointer not found — preserve the ref so the caller can diagnose it.
        return {"$ref": ref}
    return _resolve_refs(
        target, base_path, visited | {visit_key}, root_doc=root_doc, shared_refs=shared_refs, current_file=current_file
    )


def _resolve_refs(
    node: Any,
    base_path: Path,
    visited: set[str] | None = None,
    root_doc: Any = None,
    shared_refs: dict[str, str] | None = None,
    current_file: Path | None = None,
) -> Any:
    """Recursively resolve all $ref values in *node*, loading external files as needed.

    Args:
        node: The YAML node (dict / list / scalar) to process.
        base_path: Directory of the file that contains *node* (used to resolve
            relative file $refs).
        visited: Set of "file_path#/json/pointer" strings already being resolved
            (guards against infinite recursion on circular refs).
        root_doc: The root document for resolving same-file $refs (e.g.
            ``#/definitions/Foo``).  Defaults to *node* on the first call.
        shared_refs: Mapping of ``"resolved_file_path#fragment"`` to a local
            ``$ref`` string like ``"#/components/schemas/ErrorData"``.  When an
            external or same-file ref (resolved against ``current_file``) matches
            a key in this dict the local ref is returned as-is instead of
            inlining the target schema.  This prevents shared base schemas from
            being duplicated at every usage site.
        current_file: The resolved path of the file currently being processed.
            Used to check same-file ``#/…`` refs against ``shared_refs`` when
            that file is a shared base file.

    Returns:
        A new structure with all $refs resolved inline (except shared_refs).

    """
    if visited is None:
        visited = set()
    if root_doc is None:
        root_doc = node
    if shared_refs is None:
        shared_refs = {}

    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str):
            ref = node["$ref"]
            # Collect sibling properties (OpenAPI 3.1.0 allows keywords alongside $ref)
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            file_part, fragment = ref.split("#", 1) if "#" in ref else (ref, "")
            if file_part:
                resolved = _resolve_external_ref(file_part, fragment, ref, base_path, visited, shared_refs)
            else:
                resolved = _resolve_same_file_ref(
                    fragment, ref, base_path, visited, root_doc, shared_refs, current_file
                )
            # If the ref was preserved (not inlined) and there are sibling
            # properties, keep them alongside the $ref.  This is valid in
            # OpenAPI 3.1.0 (JSON Schema) where $ref can coexist with other
            # keywords like description and default.
            if siblings and isinstance(resolved, dict) and "$ref" in resolved:
                merged_node = dict(resolved)
                merged_node.update(siblings)
                return merged_node
            return resolved
        return {k: _resolve_refs(v, base_path, visited, root_doc, shared_refs, current_file) for k, v in node.items()}

    if isinstance(node, list):
        return [_resolve_refs(item, base_path, visited, root_doc, shared_refs, current_file) for item in node]

    return node


# ---------------------------------------------------------------------------
# Sub-spec discovery
# ---------------------------------------------------------------------------


def _discover_sub_specs() -> list[Path]:
    """Find all domain OpenAPI sub-specs under schemas/."""
    found: list[Path] = []
    for domain_dir in sorted(SCHEMAS_DIR.iterdir()):
        if not domain_dir.is_dir():
            continue
        if domain_dir.name in _SKIP_DIRS:
            continue

        for candidate in sorted(domain_dir.rglob("*.yaml")) + sorted(domain_dir.rglob("*.json")):
            if candidate.name in _SKIP_FILES:
                continue
            if candidate.name.startswith("websocket-"):
                continue  # AsyncAPI specs — skip
            # Only include files that look like OpenAPI specs
            try:
                data = _load_yaml(candidate)
            except yaml.YAMLError:
                continue
            if isinstance(data, dict) and "openapi" in data and "paths" in data:
                found.append(candidate)

    return found


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


def _deep_merge_components(
    target: dict[str, Any],
    source: dict[str, Any],
    source_file: Path,
) -> None:
    """Merge *source* components into *target*, erroring on unexpected name collisions."""
    for section, items in source.items():
        if not isinstance(items, dict):
            continue
        if section not in target:
            target[section] = {}
        for name, definition in items.items():
            if name in target[section]:
                if target[section][name] != definition:
                    raise ValueError(
                        f"Component name collision: '{section}/{name}' defined differently "
                        f"in {source_file} and a previously merged spec. "
                        "Rename one of the conflicting definitions."
                    )
                # Same definition — deduplication, OK
            else:
                target[section][name] = definition


def _collect_tags(
    tags: list[dict[str, Any]],
    merged_tags: list[dict[str, Any]],
    seen_tag_names: set[str],
) -> None:
    """Append tags not already seen into *merged_tags*, updating *seen_tag_names*."""
    for tag in tags:
        tag_name = tag.get("name", "")
        if tag_name and tag_name not in seen_tag_names:
            merged_tags.append(tag)
            seen_tag_names.add(tag_name)


def _load_aggregator_metadata() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return the fixed root info and servers for the merged spec."""
    root_info: dict[str, Any] = {
        "title": "Syntara API",
        "version": API_V1_VERSION,
        "description": "A distributed multi-agent workflow orchestration system",
    }
    root_servers: list[dict[str, Any]] = [{"url": "/api/v1", "description": "API v1"}]
    return root_info, root_servers


def _load_shared_refs(merged_components: dict[str, Any]) -> dict[str, str]:
    """Load base shared schemas into *merged_components* and return a ref map.

    Returns a dict mapping ``"resolved_file_path#fragment"`` keys to local
    ``$ref`` strings (e.g. ``"#/components/schemas/ErrorData"``).  This map is
    passed to ``_resolve_refs`` so that references to base schemas are kept as
    named component refs rather than being inlined at every usage site.
    """
    if not _BASE_SHARED_SCHEMAS_FILE.exists():
        return {}

    base_data = _load_yaml(_BASE_SHARED_SCHEMAS_FILE)
    base_file = _BASE_SHARED_SCHEMAS_FILE.resolve()
    shared_refs: dict[str, str] = {}

    # Only pre-load named schemas, not responses/parameters, to avoid collisions
    # with sub-specs that define their own responses under the same names.
    schemas = base_data.get("components", {}).get("schemas", {})
    if schemas:
        if "schemas" not in merged_components:
            merged_components["schemas"] = {}
        for name, definition in schemas.items():
            if name in _EXCLUDED_FROM_BUNDLE_OUTPUT:
                # Abstract base schemas: don't register as named components or in
                # shared_refs so that any $ref to them is inlined at usage sites.
                continue
            merged_components["schemas"][name] = definition
            fragment = f"/components/schemas/{name}"
            shared_refs[f"{base_file}#{fragment}"] = f"#/components/schemas/{name}"

    return shared_refs


def _strip_self_ref_exports(components: dict[str, Any]) -> dict[str, Any]:
    """Remove component entries that are self-referential re-export stubs.

    After shared-ref substitution, a sub-spec entry like::

        components:
          schemas:
            BaseResource:
              $ref: '../base/shared-resources.openapi.yaml#/components/schemas/BaseResource'

    becomes ``BaseResource: {$ref: '#/components/schemas/BaseResource'}``.
    This is a no-op re-export; the schema is already registered under that
    name in the merged output.  Keeping it would cause a false collision in
    ``_deep_merge_components``.
    """
    stripped: dict[str, Any] = {}
    for section, items in components.items():
        if not isinstance(items, dict):
            stripped[section] = items
            continue
        filtered = {
            name: definition
            for name, definition in items.items()
            if not (isinstance(definition, dict) and definition == {"$ref": f"#/components/{section}/{name}"})
        }
        if filtered:
            stripped[section] = filtered
    return stripped


def _merge_sub_spec(
    spec_path: Path,
    merged_paths: dict[str, Any],
    merged_components: dict[str, Any],
    merged_tags: list[dict[str, Any]],
    seen_tag_names: set[str],
    shared_refs: dict[str, str],
) -> None:
    """Resolve and merge a single sub-spec into the accumulated collections."""
    spec_data = _load_yaml(spec_path)
    resolved_spec_path = spec_path.resolve()

    # Extend shared_refs with this spec's own component schemas so that
    # same-file $refs like '#/components/schemas/Foo' are preserved as named
    # component refs in the bundled output instead of being inlined at every
    # usage site.
    # Parameters are intentionally excluded: FastAPI always inlines path/query
    # parameters and never emits components/parameters, so keeping them as
    # named components in the bundle causes drift. Excluding them from
    # local_shared_refs causes _resolve_same_file_ref to inline them at each
    # usage site instead of preserving the $ref.
    local_shared_refs = dict(shared_refs)
    for section, items in spec_data.get("components", {}).items():
        if isinstance(items, dict) and section != "parameters":
            for name in items:
                fragment = f"/components/{section}/{name}"
                local_shared_refs[f"{resolved_spec_path}#{fragment}"] = f"#/components/{section}/{name}"

    resolved = _resolve_refs(
        spec_data, spec_path.parent, shared_refs=local_shared_refs, current_file=resolved_spec_path
    )

    for path_key, path_item in resolved.get("paths", {}).items():
        if path_key in merged_paths:
            raise ValueError(f"Path collision: '{path_key}' defined in {spec_path} and a previously merged spec.")
        merged_paths[path_key] = path_item

    components = _strip_self_ref_exports(resolved.get("components", {}))
    # Drop parameters: inlined at usage sites above; FastAPI never emits components/parameters.
    components = {k: v for k, v in components.items() if k != "parameters"}
    _deep_merge_components(merged_components, components, spec_path)
    _collect_tags(resolved.get("tags", []), merged_tags, seen_tag_names)


def _find_schema_refs_in_text(text: str) -> set[str]:
    """Extract all ``#/components/schemas/X`` reference names from JSON text."""
    return {m.group(1) for m in re.finditer(r'"#/components/schemas/([^"]+)"', text)}


def _compute_reachable_schemas(
    seed_schemas: set[str],
    all_schemas: dict[str, Any],
) -> set[str]:
    """Compute the transitive closure of schema references starting from *seed_schemas*."""
    import json as _json

    visited: set[str] = set()
    queue = list(seed_schemas)
    while queue:
        name = queue.pop()
        if name in visited:
            continue
        visited.add(name)
        if name in all_schemas:
            schema_text = _json.dumps(all_schemas[name])
            queue.extend(r for r in _find_schema_refs_in_text(schema_text) if r not in visited)
    return visited


def _deep_merge_property(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge two property schemas: override wins for scalar keys, dicts are merged recursively."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge_property(result[k], v)
        else:
            result[k] = v
    return result


def _merge_plain_allof(schema: dict[str, Any]) -> dict[str, Any]:  # noqa: C901, PLR0912
    """Merge an allOf whose every item is a plain object into a single flat schema.

    Skips schemas where any allOf item contains a $ref or combining keyword
    (allOf/anyOf/oneOf/not), since those require proper JSON Schema resolution.
    Properties are deep-merged so domain-specific sub-keys (e.g. items) layer
    on top of base schema sub-keys (e.g. maxItems, title) for the same property.
    The outer schema's keys always take precedence over values from allOf items.
    Non-special scalar keys (e.g. title, description, additionalProperties) are
    collected from allOf items with later items overriding earlier ones, then
    applied to the result if not already set by the outer schema.
    """
    all_of = schema.get("allOf")
    if not isinstance(all_of, list) or not all_of:
        return schema

    _complex_kw = {"$ref", "allOf", "anyOf", "oneOf", "not"}
    for item in all_of:
        if not isinstance(item, dict) or any(k in item for k in _complex_kw):
            return schema

    merged_props: dict[str, Any] = {}
    merged_required: list[str] = []
    item_type: str | None = None
    item_examples: list[Any] | None = None
    item_scalars: dict[str, Any] = {}

    _special_merge_keys = {"properties", "required", "type", "examples"}

    for item in all_of:
        for prop_name, prop_schema in item.get("properties", {}).items():
            if (
                prop_name in merged_props
                and isinstance(merged_props[prop_name], dict)
                and isinstance(prop_schema, dict)
            ):
                merged_props[prop_name] = _deep_merge_property(merged_props[prop_name], prop_schema)
            else:
                merged_props[prop_name] = prop_schema
        merged_required.extend(item.get("required", []))
        if item_type is None and "type" in item:
            item_type = item["type"]
        if item_examples is None and "examples" in item:
            item_examples = item["examples"]
        item_scalars.update({k: v for k, v in item.items() if k not in _special_merge_keys})

    result = {k: v for k, v in schema.items() if k != "allOf"}
    if merged_props:
        existing = result.get("properties", {})
        result["properties"] = {**merged_props, **existing}
    if merged_required:
        existing_set = set(result.get("required", []))
        extra = [r for r in merged_required if r not in existing_set]
        if extra:
            result["required"] = list(result.get("required", [])) + extra
    if item_type is not None and "type" not in result:
        result["type"] = item_type
    if item_examples is not None and "examples" not in result:
        result["examples"] = item_examples
    for k, v in item_scalars.items():
        if k not in result:
            result[k] = v
    return result


def _flatten_plain_allof(node: Any) -> Any:
    """Recursively apply _merge_plain_allof to every dict node in the document."""
    if isinstance(node, dict):
        node = {k: _flatten_plain_allof(v) for k, v in node.items()}
        return _merge_plain_allof(node)
    if isinstance(node, list):
        return [_flatten_plain_allof(item) for item in node]
    return node


def _prune_unreferenced_shared_schemas(
    merged: dict[str, Any],
    shared_schema_names: set[str],
) -> None:
    """Remove shared base schemas not referenced by any path or non-shared schema.

    After merging, shared schemas (from shared-resources.openapi.yaml) may exist
    in the bundled output even though no sub-spec path or schema references them.
    This happens because ``_load_shared_refs`` pre-loads all shared schemas.
    """
    if not shared_schema_names:
        return
    schemas = merged.get("components", {}).get("schemas", {})
    if not schemas:
        return

    import json as _json

    paths_text = _json.dumps(merged.get("paths", {}))
    used_schemas = _find_schema_refs_in_text(paths_text)
    reachable = _compute_reachable_schemas(used_schemas, schemas)

    for name in list(shared_schema_names):
        if name not in reachable and name in schemas:
            del schemas[name]


def _build_merged_spec(sub_specs: list[Path]) -> dict[str, Any]:
    """Load, resolve, and merge all sub-specs into a single OpenAPI document."""
    merged_paths: dict[str, Any] = {}
    merged_components: dict[str, Any] = {}
    merged_tags: list[dict[str, Any]] = []
    seen_tag_names: set[str] = set()

    root_info, root_servers = _load_aggregator_metadata()

    # Pre-load base shared schemas so they appear as named components in the
    # bundled output and are referenced (not inlined) wherever used.
    shared_refs = _load_shared_refs(merged_components)

    # Track which schema names came from shared-resources
    shared_schema_names = set(merged_components.get("schemas", {}).keys())

    for spec_path in sub_specs:
        _merge_sub_spec(spec_path, merged_paths, merged_components, merged_tags, seen_tag_names, shared_refs)

    merged: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": root_info,
        "servers": root_servers,
    }
    if merged_tags:
        merged["tags"] = merged_tags
    merged["paths"] = merged_paths
    if merged_components:
        merged["components"] = merged_components

    # Remove shared schemas that are no longer referenced by any path or sub-spec schema
    _prune_unreferenced_shared_schemas(merged, shared_schema_names)

    # Merge allOf of plain objects into flat schemas
    return _flatten_plain_allof(merged)


# ---------------------------------------------------------------------------
# YAML output helpers
# ---------------------------------------------------------------------------


class _LiteralStr(str):
    """Marker class for multiline strings to be rendered with literal block style."""

    __slots__ = ()


def _literal_representer(dumper: yaml.Dumper, data: _LiteralStr) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


def _str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _build_dumper() -> type[yaml.Dumper]:
    dumper = yaml.Dumper
    dumper.add_representer(_LiteralStr, _literal_representer)
    dumper.add_representer(str, _str_representer)
    return dumper


GENERATED_HEADER = """\
# =============================================================================
# DO NOT EDIT — this file is generated by `make api-spec-bundle`.
#
# Source: tools/bundle_openapi.py
# Sub-specs: src/syntara/schemas/*/openapi.yaml  (and *.openapi.yaml variants)
#
# To update: edit the relevant domain sub-spec, then run:
#   make api-spec-bundle
# =============================================================================
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Output file path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the merged spec to stdout without writing to disk",
    )
    parser.add_argument(
        "--list-specs",
        action="store_true",
        help="List discovered sub-specs and exit",
    )
    return parser.parse_args()


def main() -> None:
    """Discover sub-specs, merge them, and write the bundled OpenAPI document."""
    args = _parse_args()

    sub_specs = _discover_sub_specs()

    if args.list_specs:
        print("Discovered sub-specs:")
        for p in sub_specs:
            print(f"  {p.relative_to(PROJECT_ROOT)}")
        return

    if not sub_specs:
        sys.exit("No sub-specs found under src/syntara/schemas/. Nothing to bundle.")

    print(f"Bundling {len(sub_specs)} sub-spec(s)...")
    for p in sub_specs:
        print(f"  {p.relative_to(PROJECT_ROOT)}")

    merged = _build_merged_spec(sub_specs)

    output_yaml = yaml.dump(
        merged,
        Dumper=_build_dumper(),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )
    # Strip trailing spaces/tabs from each line (yaml.dump can leave them).
    # Use [ \t] instead of \s to avoid stripping blank lines (which are
    # significant in YAML literal block scalars for preserving \n\n).
    output_yaml = re.sub(r"[ \t]+$", "", output_yaml, flags=re.MULTILINE)

    full_output = GENERATED_HEADER + output_yaml

    if args.dry_run:
        print(full_output)
        return

    output_path = Path(args.output).resolve()
    output_path.write_text(full_output, encoding="utf-8")
    print(f"\nBundled spec written to: {output_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
