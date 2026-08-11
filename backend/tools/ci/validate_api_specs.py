"""Static validator for OpenAPI and AsyncAPI specification files.

Validates spec files against project conventions without requiring
the application to be running. Checks include:

OpenAPI:
- Parse validation (valid YAML/JSON)
- operationId presence on all endpoints
- API prefix convention (/api/v{version}/{domain})
- Corresponding router module existence

AsyncAPI/WebSocket:
- Parse validation (valid YAML/JSON)
- Orphan specs (spec without handler)
- Missing specs (handler without spec)
- Channel naming convention (snake_case)
- Channel address format (/ws/{component}/v1/{channel})
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import yaml

if TYPE_CHECKING:
    from collections.abc import Sequence

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

SEPARATOR = "=" * 70
DASH_SEPARATOR = "-" * 70

# Files that are not OpenAPI endpoint specs (shared schemas, non-API specs)
OPENAPI_IGNORE_FILES = {
    "shared-resources.openapi.yaml",
    "shared-schemas.yaml",
    "workflow-websocket-api.yaml",
}

# Directories within schemas/ that don't represent API domains
SCHEMA_IGNORE_DIRS = {"base", "internal_metrics", "schemas", "v2"}

# Maps schema domain names to their Python module domain when they differ.
# Used when a schema lives in its own folder (e.g. schemas/executions/) but
# the implementing router is in a different Python domain (e.g. workflows/).
SCHEMA_DOMAIN_TO_PYTHON_DOMAIN: dict[str, str] = {
    "executions": "workflows",
}


def find_project_root() -> Path:
    """Find the project root by looking for pyproject.toml."""
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    sys.stderr.write(f"{RED}Could not find project root (no pyproject.toml found){RESET}\n")
    sys.exit(1)


def load_spec_file(path: Path) -> dict[str, Any] | None:
    """Load a YAML or JSON spec file, returning None on parse errors."""
    try:
        content = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            result: dict[str, Any] = yaml.safe_load(content)
            return result
        if path.suffix == ".json":
            result_json: dict[str, Any] = json.loads(content)
            return result_json
        return None
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        return {"__parse_error__": str(e)}


def is_openapi_spec(data: dict[str, Any]) -> bool:
    """Check if a parsed spec is an OpenAPI spec."""
    return "openapi" in data and "paths" in data


def is_asyncapi_spec(data: dict[str, Any]) -> bool:
    """Check if a parsed spec is an AsyncAPI spec."""
    return "asyncapi" in data and "channels" in data


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_openapi_specs(schemas_dir: Path) -> list[Path]:
    """Find all candidate OpenAPI spec files under schemas/.

    Returns all YAML/JSON files that are not explicitly ignored or websocket specs.
    The actual OpenAPI check is deferred to validate_openapi_specs() so that
    malformed files are reported instead of silently skipped.
    """
    specs = []
    for path in sorted(schemas_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in (".yaml", ".yml", ".json"):
            continue
        if path.name in OPENAPI_IGNORE_FILES:
            continue
        if path.name.startswith("websocket-"):
            continue
        specs.append(path)
    return specs


def discover_asyncapi_specs(schemas_dir: Path) -> list[Path]:
    """Find all AsyncAPI websocket spec files under schemas/."""
    specs: set[Path] = set()
    for ext in ("*.yaml", "*.yml", "*.json"):
        specs.update(path for path in schemas_dir.rglob(f"websocket-{ext}") if path.is_file())
    return sorted(specs)


def discover_ws_handlers(src_dir: Path) -> list[Path]:
    """Find all WebSocket handler .py files (excluding __init__.py)."""
    handlers: list[Path] = []
    for ws_dir in sorted(src_dir.rglob("ws")):
        if not ws_dir.is_dir():
            continue
        handlers.extend(py_file for py_file in sorted(ws_dir.glob("*.py")) if py_file.name != "__init__.py")
    return handlers


# ---------------------------------------------------------------------------
# OpenAPI Validation
# ---------------------------------------------------------------------------


def extract_base_path(spec_data: dict[str, Any]) -> str:
    """Extract the common base path from server URLs."""
    servers = spec_data.get("servers", [])
    if not servers:
        return ""

    paths = []
    for server in servers:
        url = server.get("url", "")
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        # Handle relative URLs (e.g., "/api/v1")
        if not parsed.scheme and not parsed.netloc:
            path = url.rstrip("/")
        paths.append(path)

    paths = [p for p in paths if p]
    if not paths:
        return ""

    if len(paths) == 1:
        return str(paths[0])

    # Find longest common prefix by segments
    split_paths = [p.split("/") for p in paths]
    common = []
    for segments in zip(*split_paths, strict=False):
        if len(set(segments)) == 1:
            common.append(segments[0])
        else:
            break
    return "/".join(common)


def extract_domain(spec_path: Path, schemas_dir: Path) -> str:
    """Extract the domain name from an OpenAPI spec path.

    Supports:
    - schemas/{domain}/openapi.{ext} -> domain from parent dir
    - schemas/{domain}/{name}_openapi.{ext} -> {name} from filename
    - schemas/{domain}/{domain}.{ext} -> domain from filename
    """
    rel = spec_path.relative_to(schemas_dir)
    parent_name = rel.parent.name if str(rel.parent) != "." else ""

    if spec_path.stem == "openapi":
        return parent_name

    if spec_path.stem.endswith("_openapi"):
        return spec_path.stem.replace("_openapi", "")

    return parent_name or spec_path.stem


def _validate_openapi_endpoints(data: dict[str, Any], rel_path: Path, base_path: str, errors: list[str]) -> None:
    """Validate operationId and API prefix for all endpoints in an OpenAPI spec."""
    api_prefix_pattern = re.compile(r"^/api/v\d+/")

    paths = data.get("paths", {})
    if not isinstance(paths, dict):
        errors.append(f"  - {rel_path}\n    'paths' must be an object")
        return

    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            errors.append(f"  - {rel_path}\n    Path item for '{path_str}' must be an object")
            continue
        for method in ("get", "post", "put", "delete", "patch", "options", "head"):
            if method not in path_item:
                continue
            operation = path_item[method]
            if not isinstance(operation, dict):
                errors.append(f"  - {rel_path}\n    Operation for {method.upper()} {path_str} must be an object")
                continue
            full_path = f"{base_path}{path_str}" if base_path else path_str

            if not operation.get("operationId"):
                errors.append(f"  - {rel_path}\n    Missing operationId for {method.upper()} {full_path}")

            if not api_prefix_pattern.match(full_path):
                errors.append(
                    f"  - {rel_path}\n"
                    f"    Invalid API prefix for {method.upper()} {full_path}\n"
                    f"    Expected pattern: /api/v{{version}}/{{domain}}/..."
                )


def _validate_openapi_router(spec_path: Path, rel_path: Path, src_dir: Path, errors: list[str]) -> None:
    """Validate that a corresponding router module exists for the spec's component."""
    schema_domain = spec_path.parent.name
    if schema_domain in SCHEMA_IGNORE_DIRS:
        return

    # Resolve the Python domain (may differ from schema domain)
    python_domain = SCHEMA_DOMAIN_TO_PYTHON_DOMAIN.get(schema_domain, schema_domain)

    # For remapped domains, look for a sub-router named {schema_domain}_router.py
    # (e.g., schema domain "executions" maps to workflows/executions_router.py)
    if python_domain != schema_domain:
        router_path = src_dir / python_domain / f"{schema_domain}_router.py"
        if not router_path.is_file():
            errors.append(
                f"  - {rel_path}\n"
                f"    No router module found for component '{schema_domain}'\n"
                f"    Expected: src/syntara/{python_domain}/{schema_domain}_router.py"
            )
        return

    router_path = src_dir / python_domain / "router.py"
    alt_router_path = src_dir / python_domain / f"{python_domain}_router.py"
    if not router_path.is_file() and not alt_router_path.is_file():
        errors.append(
            f"  - {rel_path}\n"
            f"    No router module found for component '{python_domain}'\n"
            f"    Expected: src/syntara/{python_domain}/router.py"
        )


def validate_openapi_specs(specs: list[Path], schemas_dir: Path, src_dir: Path) -> list[str]:
    """Validate all OpenAPI spec files. Returns list of error messages."""
    errors: list[str] = []
    project_root = schemas_dir.parent.parent.parent

    for spec_path in specs:
        rel_path = spec_path.relative_to(project_root)
        data = load_spec_file(spec_path)

        if data is None:
            errors.append(f"  - {rel_path}\n    Could not load file (unsupported format)")
            continue

        if "__parse_error__" in data:
            errors.append(f"  - {rel_path}\n    Parse error: {data['__parse_error__']}")
            continue

        if not is_openapi_spec(data):
            continue

        if spec_path.parent.name in SCHEMA_IGNORE_DIRS:
            continue

        base_path = extract_base_path(data)
        _validate_openapi_endpoints(data, rel_path, base_path, errors)
        _validate_openapi_router(spec_path, rel_path, src_dir, errors)

    return errors


# ---------------------------------------------------------------------------
# AsyncAPI / WebSocket Validation
# ---------------------------------------------------------------------------


def spec_to_handler_path(spec_path: Path, src_dir: Path) -> Path:
    """Map spec path to expected handler path.

    websocket-{name}.yaml -> src/syntara/{component}/ws/{name}.py
    """
    component_name = spec_path.parent.name
    handler_stem = spec_path.stem[len("websocket-") :]
    return src_dir / component_name / "ws" / f"{handler_stem}.py"


def handler_to_spec_stem(handler_path: Path) -> str:
    """Map handler path to expected spec filename stem.

    {name}.py -> websocket-{name}
    """
    return f"websocket-{handler_path.stem}"


def is_snake_case(name: str) -> bool:
    """Check if a name follows snake_case convention."""
    return bool(re.match(r"^[a-z][a-z0-9_]*$", name))


def normalize_channel_name(name: str) -> str:
    """Convert kebab-case channel name to snake_case."""
    return name.replace("-", "_")


def _validate_asyncapi_channels(
    data: dict[str, Any], rel_path: Path, component_name: str, pathname: str, errors: list[str]
) -> None:
    """Validate channel naming and address format in an AsyncAPI spec."""
    channels = data.get("channels", {})
    if not isinstance(channels, dict):
        errors.append(f"  - {rel_path}\n    'channels' must be an object")
        return
    for channel_name, channel_def in channels.items():
        if not is_snake_case(channel_name):
            normalized = normalize_channel_name(channel_name)
            errors.append(
                f"  - {rel_path}\n    Channel '{channel_name}' should be '{normalized}' (snake_case convention)"
            )

        address = channel_def.get("address", "") if isinstance(channel_def, dict) else ""
        if not address:
            errors.append(f"  - {rel_path}\n    Channel '{channel_name}' is missing 'address' field")
            continue

        normalized_channel = normalize_channel_name(channel_name)
        expected_prefix = f"{pathname}/ws/{component_name}/v1/{normalized_channel}"
        base_address = re.sub(r"\{[^}]+\}", "", address)
        if not base_address.startswith(expected_prefix):
            errors.append(
                f"  - {rel_path}\n"
                f"    Channel '{channel_name}' address mismatch\n"
                f"    Expected to start with: {expected_prefix}\n"
                f"    Got: {address}"
            )


def validate_asyncapi_specs(specs: list[Path], project_root: Path) -> list[str]:
    """Validate AsyncAPI spec files (parse, naming, addresses). Returns error messages."""
    errors: list[str] = []

    for spec_path in specs:
        rel_path = spec_path.relative_to(project_root)
        data = load_spec_file(spec_path)

        if data is None:
            errors.append(f"  - {rel_path}\n    Could not load file (unsupported format)")
            continue

        if "__parse_error__" in data:
            errors.append(f"  - {rel_path}\n    Parse error: {data['__parse_error__']}")
            continue

        if not is_asyncapi_spec(data):
            errors.append(f"  - {rel_path}\n    Not a valid AsyncAPI spec (missing 'asyncapi' or 'channels')")
            continue

        component_name = spec_path.parent.name

        # Extract optional server pathname
        pathname = ""
        try:
            servers = data.get("servers", {})
            dev = servers.get("development", {})
            pathname = (dev.get("pathname", "") or "").rstrip("/")
        except (AttributeError, TypeError):
            pass

        # Validate channels
        _validate_asyncapi_channels(data, rel_path, component_name, pathname, errors)

    return errors


def validate_handler_spec_pairs(
    asyncapi_specs: list[Path],
    ws_handlers: list[Path],
    schemas_dir: Path,
    src_dir: Path,
    project_root: Path,
) -> tuple[list[str], list[str]]:
    """Check for orphan specs and missing specs. Returns (orphan_errors, missing_errors)."""
    orphan_errors: list[str] = []
    missing_errors: list[str] = []

    # Build lookup sets
    spec_set: dict[Path, Path] = {}  # expected_handler -> spec_path
    for spec_path in asyncapi_specs:
        expected_handler = spec_to_handler_path(spec_path, src_dir)
        spec_set[expected_handler] = spec_path

    handler_set: dict[str, Path] = {}  # "component/handler_stem" -> handler_path
    for handler_path in ws_handlers:
        component = handler_path.parent.parent.name  # .../component/ws/name.py
        key = f"{component}/{handler_path.stem}"
        handler_set[key] = handler_path

    # Check for orphan specs (spec without handler)
    for expected_handler, spec_path in spec_set.items():
        if not expected_handler.exists():
            rel_spec = spec_path.relative_to(project_root)
            rel_handler = expected_handler.relative_to(project_root)
            orphan_errors.append(f"  - Spec: {rel_spec}\n    Expected handler: {rel_handler}")

    # Check for missing specs (handler without spec)
    for handler_path in ws_handlers:
        component = handler_path.parent.parent.name
        handler_stem = handler_path.stem
        # Check if any spec maps to this handler
        found = False
        for ext in (".yaml", ".yml", ".json"):
            candidate = schemas_dir / component / f"websocket-{handler_stem}{ext}"
            if candidate.exists():
                found = True
                break
        if not found:
            rel_handler = handler_path.relative_to(project_root)
            expected_spec = f"schemas/{component}/websocket-{handler_stem}.yaml"
            missing_errors.append(f"  - Handler: {rel_handler}\n    Expected spec: src/syntara/{expected_spec}")

    return orphan_errors, missing_errors


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_error_block(title: str, items: Sequence[str], fix_options: Sequence[str] | None = None) -> str:
    """Format an error block matching the project's error output style."""
    lines = [
        f"\n{SEPARATOR}",
        f"{RED}{BOLD}{title}{RESET}",
        SEPARATOR,
        "",
    ]

    count = len(items)
    noun = "issue" if count == 1 else "issues"
    lines.append(f"Found {count} {noun}:\n")

    for item in items:
        lines.append(item)
        lines.append("")

    if fix_options:
        lines.append(DASH_SEPARATOR)
        lines.append("How to fix:\n")
        for i, option in enumerate(fix_options, 1):
            lines.append(f"  Option {i}: {option}")
        lines.append("")

    lines.append(SEPARATOR)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all API spec validations. Returns exit code."""
    project_root = find_project_root()
    src_dir = project_root / "src" / "syntara"
    schemas_dir = src_dir / "schemas"

    if not schemas_dir.exists():
        sys.stderr.write(f"{RED}Schemas directory not found: {schemas_dir}{RESET}\n")
        return 1

    # Discover specs and handlers
    openapi_specs = discover_openapi_specs(schemas_dir)
    asyncapi_specs = discover_asyncapi_specs(schemas_dir)
    ws_handlers = discover_ws_handlers(src_dir)

    all_errors: list[str] = []

    # --- OpenAPI validation ---
    openapi_errors = validate_openapi_specs(openapi_specs, schemas_dir, src_dir)
    if openapi_errors:
        block = format_error_block(
            "OpenAPI Specification Errors",
            openapi_errors,
            fix_options=[
                "Add missing operationId to each endpoint operation",
                "Ensure paths follow /api/v{version}/{domain}/... convention",
                "Create the missing router module for the domain",
            ],
        )
        sys.stderr.write(block + "\n")
        all_errors.extend(openapi_errors)

    # --- AsyncAPI validation ---
    asyncapi_errors = validate_asyncapi_specs(asyncapi_specs, project_root)
    if asyncapi_errors:
        block = format_error_block(
            "AsyncAPI Specification Errors",
            asyncapi_errors,
            fix_options=[
                "Use snake_case for channel names (e.g., 'agent_events' not 'agent-events')",
                "Set channel address to /ws/{component}/v1/{channel_name}",
            ],
        )
        sys.stderr.write(block + "\n")
        all_errors.extend(asyncapi_errors)

    # --- Handler-spec pairing ---
    orphan_errors, missing_errors = validate_handler_spec_pairs(
        asyncapi_specs, ws_handlers, schemas_dir, src_dir, project_root
    )

    if orphan_errors:
        block = format_error_block(
            "WebSocket Configuration Error: Orphan Spec File(s) Detected",
            orphan_errors,
            fix_options=[
                "Create the missing handler file\n"
                "            The handler filename must match the spec filename:\n"
                "            websocket-{name}.yaml -> {name}.py",
                "Remove the orphan spec file if it's no longer needed",
            ],
        )
        sys.stderr.write(block + "\n")
        all_errors.extend(orphan_errors)

    if missing_errors:
        block = format_error_block(
            "WebSocket Configuration Error: Missing Spec File(s)",
            missing_errors,
            fix_options=[
                "Create the missing spec file at the expected path\n"
                "            Supported extensions: .yaml, .yml, .json",
                "Remove the handler file if it's no longer needed",
            ],
        )
        sys.stderr.write(block + "\n")
        all_errors.extend(missing_errors)

    # --- Summary ---
    total_specs = len(openapi_specs) + len(asyncapi_specs)
    total_handlers = len(ws_handlers)

    if all_errors:
        sys.stderr.write(
            f"\n{RED}FAILED{RESET}: {len(all_errors)} API validation error(s) "
            f"({len(openapi_specs)} OpenAPI specs, {len(asyncapi_specs)} AsyncAPI specs, "
            f"{total_handlers} WebSocket handlers checked)\n"
        )
        return 1

    sys.stdout.write(
        f"{GREEN}SUCCESS{RESET}: All API specs validated "
        f"({len(openapi_specs)} OpenAPI, {len(asyncapi_specs)} AsyncAPI, "
        f"{total_handlers} handlers, {total_specs} total specs)\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
