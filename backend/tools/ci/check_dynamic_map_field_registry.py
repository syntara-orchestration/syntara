"""Ensure dynamic-map field names in OpenAPI specs stay registered for policy checks.

Scans domain OpenAPI sources for labels-style dynamic-map properties (``labels``,
``result``, or ``*_data`` object maps) and fails when a new field is not listed
in ``DYNAMIC_MAP_FIELD_NAMES`` inside ``scripts/openapi/dynamic_map_policy.py``.

Usage:
    uv run python tools/ci/check_dynamic_map_field_registry.py
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = ROOT / "src" / "syntara" / "schemas"
SCRIPTS_OPENAPI = ROOT / "scripts" / "openapi"
sys.path.insert(0, str(SCRIPTS_OPENAPI))

from dynamic_map_policy import (  # noqa: E402
    DYNAMIC_MAP_FIELD_NAMES,
    REGISTRY_SCAN_IGNORE_GLOBS,
    collect_policy_registry_field_names,
)

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def _should_scan(path: Path) -> bool:
    rel = path.relative_to(SCHEMAS_DIR)
    name = rel.name
    rel_str = str(rel)
    return not any(
        fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_str, pattern) for pattern in REGISTRY_SCAN_IGNORE_GLOBS
    )


def _load_yaml(path: Path) -> dict | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"{RED}ERROR: Failed to parse {path}: {exc}{RESET}", file=sys.stderr)
        return None
    return data if isinstance(data, dict) else None


def find_unregistered_fields() -> tuple[set[str], dict[str, set[str]]]:
    """Return unregistered field names and where they were found."""
    discovered: dict[str, set[str]] = {}

    for path in sorted(SCHEMAS_DIR.rglob("*.yaml")):
        if not _should_scan(path):
            continue
        data = _load_yaml(path)
        if data is None:
            continue
        rel = str(path.relative_to(ROOT))
        for field_name in collect_policy_registry_field_names(data):
            discovered.setdefault(field_name, set()).add(rel)

    unregistered = set(discovered) - set(DYNAMIC_MAP_FIELD_NAMES)
    return unregistered, discovered


def find_stale_registry_entries(discovered: dict[str, set[str]]) -> set[str]:
    """Return registry entries that no longer appear in scanned OpenAPI sources."""
    return set(DYNAMIC_MAP_FIELD_NAMES) - set(discovered)


def main() -> int:
    """Run the dynamic-map field registry check."""
    unregistered, discovered = find_unregistered_fields()
    stale = find_stale_registry_entries(discovered)
    errors: list[str] = []

    if unregistered:
        details = []
        for name in sorted(unregistered):
            locations = ", ".join(sorted(discovered[name]))
            details.append(f"  - {name} (found in: {locations})")
        errors.append(
            "Unregistered dynamic-map fields detected in OpenAPI specs.\n"
            "Add each name to DYNAMIC_MAP_FIELD_NAMES in "
            "scripts/openapi/dynamic_map_policy.py:\n" + "\n".join(details)
        )

    if stale:
        stale_list = ", ".join(sorted(stale))
        print(
            f"{YELLOW}Warning: stale entries in DYNAMIC_MAP_FIELD_NAMES "
            f"(not found in scanned OpenAPI sources): {stale_list}. "
            "Remove them when unused or keep them if the field is exported only "
            f"into the bundled spec.{RESET}"
        )

    if errors:
        print(f"{RED}Dynamic-map field registry check failed:{RESET}", file=sys.stderr)
        for error in errors:
            print(f"\n{error}", file=sys.stderr)
        return 1

    print(f"{GREEN}Dynamic-map field registry check passed{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
