"""Check that the committed OpenAPI spec matches the generated one.

Reads the generated spec from stdin and compares it against a commited one. Fails if they differ
semantically (key order and YAML formatting are ignored; only the parsed content is compared).
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

import yaml

# Tags are metadata managed in sub-specs / bundle_openapi.py,
# not derived from the FastAPI implementation; exclude them from the diff.
_EXCLUDED_KEYS: frozenset[str] = frozenset({"tags"})

# Operation-level extension keys authored in sub-specs but not emitted by
# FastAPI's OpenAPI generator.  Stripping these avoids false-positive drift.
_EXCLUDED_OPERATION_KEYS: frozenset[str] = frozenset({"x-app-permission"})

# Fields where whitespace and backtick-style differences are normalized before comparison.
# This avoids false positives from YAML block-scalar vs Python triple-quoted-string formatting.
_TEXT_NORMALIZE_KEYS: frozenset[str] = frozenset({"description", "summary"})

# Valid values for the OpenAPI "in" field on parameter objects.
# Used to distinguish parameters from other objects that incidentally have "name" and "in" keys
# (e.g. security scheme objects: {type: apiKey, in: header, name: X-API-Key}).
_PARAM_IN_VALUES: frozenset[str] = frozenset({"query", "path", "header", "cookie"})


def _normalize_text(text: str) -> str:
    """Collapse whitespace runs and normalize RST ``backticks`` → `backticks` for comparison."""
    return re.sub(r"\s+", " ", text).strip().replace("``", "`")


def _is_parameter_object(obj: dict) -> bool:
    return "name" in obj and obj.get("in") in _PARAM_IN_VALUES


def _strip_descriptions_recursive(obj: object) -> object:
    """Recursively remove all 'description' keys from a schema tree."""
    if isinstance(obj, dict):
        return {k: _strip_descriptions_recursive(v) for k, v in obj.items() if k != "description"}
    if isinstance(obj, list):
        return [_strip_descriptions_recursive(item) for item in obj]
    return obj


def _strip_schema_description(param: dict) -> dict:
    """Remove descriptions from a parameter object before comparison.

    Strips descriptions at all levels: top-level parameter description,
    schema-level description, and descriptions nested inside allOf/properties
    (e.g., in deepObject filter params where sub-specs have hand-authored
    descriptions that the generated spec omits).
    """
    schema = param.get("schema")
    if isinstance(schema, dict):
        param = {**param, "schema": _strip_descriptions_recursive(schema)}
    if param.get("in") in ("query", "path") and "description" in param:
        param = {k: v for k, v in param.items() if k != "description"}
    return param


def _normalize_for_display(obj: object) -> object:
    """Strip ignored fields from parameter objects before rendering the diff.

    Mirrors the suppression logic in _normalize_for_comparison so that the
    displayed diff only shows differences that actually matter for the check.
    Unlike _normalize_for_comparison, this does NOT collapse whitespace in text
    fields — the raw values are preserved for readability.
    """
    if isinstance(obj, dict):
        if _is_parameter_object(obj):
            obj = _strip_schema_description(obj)
        return {k: _normalize_for_display(v) for k, v in obj.items() if k not in _EXCLUDED_OPERATION_KEYS}
    if isinstance(obj, list):
        return [_normalize_for_display(item) for item in obj]
    return obj


def _normalize_for_comparison(obj: object) -> object:
    """Recursively normalize description/summary text fields for equality comparison."""
    if isinstance(obj, dict):
        if _is_parameter_object(obj):
            obj = _strip_schema_description(obj)
        return {
            k: _normalize_text(v) if k in _TEXT_NORMALIZE_KEYS and isinstance(v, str) else _normalize_for_comparison(v)
            for k, v in obj.items()
            if k not in _EXCLUDED_OPERATION_KEYS
        }
    if isinstance(obj, list):
        return [_normalize_for_comparison(item) for item in obj]
    return obj


_VERBOSITY_DETAILED = 1
_VERBOSITY_FULL_DIFF = 2

_INDICATORS: dict[str, str] = {
    "removed": "✓ spec  →  ✗ generated",
    "modified": "✓ spec  →  ~ generated",
    "added": "✗ spec  →  ✓ generated",
}


def _to_yaml_text(data: object) -> str:
    return yaml.dump(data, default_flow_style=False, sort_keys=True, allow_unicode=True)


def _subkey_diffs(committed_val: object, generated_val: object) -> dict[str, list[str]]:
    """Return added/modified/removed sub-keys between two dicts."""
    c = committed_val if isinstance(committed_val, dict) else {}
    g = generated_val if isinstance(generated_val, dict) else {}
    c_norm = _normalize_for_comparison(c)
    g_norm = _normalize_for_comparison(g)
    if not isinstance(c_norm, dict) or not isinstance(g_norm, dict):
        return {"added": [], "modified": [], "removed": []}
    result: dict[str, list[str]] = {"added": [], "modified": [], "removed": []}
    for sub in sorted(c.keys() | g.keys()):
        if sub in c and sub not in g:
            result["removed"].append(sub)
        elif sub not in c and sub in g:
            result["added"].append(sub)
        elif c_norm.get(sub) != g_norm.get(sub):
            result["modified"].append(sub)
    return result


def _prepare_subkey_items(
    committed_val: object, generated_val: object
) -> tuple[list[tuple[str, str]], int, dict, dict] | None:
    """Compute diff items for two sub-spec values; return None if no differences."""
    diffs = _subkey_diffs(committed_val, generated_val)
    if not any(diffs.values()):
        return None
    items = sorted(
        [(name, status) for status, names in diffs.items() for name in names],
        key=lambda x: x[0],
    )
    col_width = max(len(name) for name, _ in items)
    c = committed_val if isinstance(committed_val, dict) else {}
    g = generated_val if isinstance(generated_val, dict) else {}
    return items, col_width, c, g


def _print_subkey_diffs(label: str, committed_val: object, generated_val: object) -> None:
    prepared = _prepare_subkey_items(committed_val, generated_val)
    if prepared is None:
        return
    items, col_width, _, _ = prepared
    print(f"\n  {label}:", file=sys.stderr)
    for name, status in items:
        print(f"    {name:<{col_width}}  {_INDICATORS[status]}", file=sys.stderr)


def _key_status(committed: dict | None, generated: dict | None, key: str) -> str:
    in_committed = committed is not None and key in committed
    in_generated = generated is not None and key in generated
    if in_committed and not in_generated:
        return "removed"
    if in_generated and not in_committed:
        return "added"
    return "modified"


def _print_detailed_changes(
    differing_keys: list[str],
    committed_dict: dict,
    generated_dict: dict,
) -> None:
    print("\n--- detailed changes ---", file=sys.stderr)
    for key in differing_keys:
        c_val = committed_dict.get(key)
        g_val = generated_dict.get(key)
        if key in ("info", "paths"):
            _print_subkey_diffs(key, c_val, g_val)
        elif key == "components":
            c_comp = c_val if isinstance(c_val, dict) else {}
            g_comp = g_val if isinstance(g_val, dict) else {}
            for section in sorted(c_comp.keys() | g_comp.keys()):
                _print_subkey_diffs(f"components/{section}", c_comp.get(section), g_comp.get(section))
        else:
            status = _key_status(committed_dict, generated_dict, key)
            print(f"\n  {key}: {status}", file=sys.stderr)


def _print_subkey_full_diff(label: str, committed_val: object, generated_val: object) -> None:
    prepared = _prepare_subkey_items(committed_val, generated_val)
    if prepared is None:
        return
    items, col_width, c, g = prepared
    print(f"\n  {label}:", file=sys.stderr)
    for name, status in items:
        print(f"    {name:<{col_width}}  {_INDICATORS[status]}", file=sys.stderr)
        c_lines = _to_yaml_text(_normalize_for_display(c.get(name))).splitlines(keepends=True)
        g_lines = _to_yaml_text(_normalize_for_display(g.get(name))).splitlines(keepends=True)
        for line in difflib.unified_diff(c_lines, g_lines, fromfile="committed", tofile="generated", n=2):
            sys.stderr.write(f"      {line}")


def _print_full_diff(differing_keys: list[str], committed_dict: dict, generated_dict: dict) -> None:
    print("\n--- full diff ---", file=sys.stderr)
    for key in differing_keys:
        c_val = committed_dict.get(key)
        g_val = generated_dict.get(key)
        if key in ("info", "paths"):
            _print_subkey_full_diff(key, c_val, g_val)
        elif key == "components":
            c_comp = c_val if isinstance(c_val, dict) else {}
            g_comp = g_val if isinstance(g_val, dict) else {}
            for section in sorted(c_comp.keys() | g_comp.keys()):
                _print_subkey_full_diff(f"components/{section}", c_comp.get(section), g_comp.get(section))
        else:
            status = _key_status(committed_dict, generated_dict, key)
            print(f"\n  {key}  {_INDICATORS[status]}", file=sys.stderr)
            c_lines = _to_yaml_text(_normalize_for_display(c_val)).splitlines(keepends=True)
            g_lines = _to_yaml_text(_normalize_for_display(g_val)).splitlines(keepends=True)
            for line in difflib.unified_diff(c_lines, g_lines, fromfile="committed", tofile="generated", n=2):
                sys.stderr.write(f"    {line}")


def _print_summary(all_keys: list[str], differing_keys: list[str], committed_spec: Path) -> None:
    summary_fields = [k for k in all_keys if k not in _EXCLUDED_KEYS]
    print("\n--- summary ---", file=sys.stderr)
    for field in summary_fields:
        changed = field in differing_keys
        status = "changed" if changed else "ok"
        mark = "❌" if changed else "✅"
        print(f"  {mark} {field}: {status}", file=sys.stderr)

    print(
        f"\n❌ The changes introduced are not captured in the OpenAPI spec under"
        f" {committed_spec}. Update the corresponding OpenAPI spec fragment or"
        f" fix the changes so they align with the spec.",
        file=sys.stderr,
    )


def main() -> int:
    """Compare committed OpenAPI spec against generated one; return 0 if they match."""
    parser = argparse.ArgumentParser(description="Check committed OpenAPI spec matches generated one")
    parser.add_argument("committed_spec", type=Path, help="Path to the committed OpenAPI spec file")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Verbosity: -v adds compact diff, -vv adds full diff",
    )
    args = parser.parse_args()

    verbosity: int = args.verbose
    committed_spec: Path = args.committed_spec

    if not committed_spec.exists():
        print(f"ERROR: committed spec not found at {committed_spec}", file=sys.stderr)
        return 1

    committed = yaml.safe_load(committed_spec.read_text(encoding="utf-8"))
    generated = yaml.safe_load(sys.stdin.read())

    committed_dict = committed if isinstance(committed, dict) else {}
    generated_dict = generated if isinstance(generated, dict) else {}

    # Normalize text fields for comparison only; originals are kept for display.
    committed_norm = _normalize_for_comparison(committed_dict)
    generated_norm = _normalize_for_comparison(generated_dict)
    if not isinstance(committed_norm, dict) or not isinstance(generated_norm, dict):
        return 0

    all_keys = sorted(committed_dict.keys() | generated_dict.keys())
    differing_keys: list[str] = [
        key for key in all_keys if key not in _EXCLUDED_KEYS and committed_norm.get(key) != generated_norm.get(key)
    ]

    if not differing_keys:
        print("✅ OpenAPI spec is up to date.")
        return 0

    if verbosity >= _VERBOSITY_DETAILED:
        _print_detailed_changes(differing_keys, committed_dict, generated_dict)

    if verbosity >= _VERBOSITY_FULL_DIFF:
        _print_full_diff(differing_keys, committed_dict, generated_dict)

    _print_summary(all_keys, differing_keys, committed_spec)
    return 1


if __name__ == "__main__":
    sys.exit(main())
