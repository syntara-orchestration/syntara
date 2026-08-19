"""Simplify OpenAPI spec for Python client generation.

Strips the base-type allOf item from deepObject filter parameters so that
``openapi-python-client`` can parse them.  The allOf pattern
``[{type: string}, {type: object, properties: ...}]`` is valid for
TypeScript codegen (produces intersection types) but ``openapi-python-client``
rejects mixed-type allOf with "Cannot take allOf a non-object".

Usage:
    uv run python tools/simplify_spec_for_client.py INPUT_SPEC OUTPUT_SPEC
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def _simplify_filter_params(spec: dict[str, Any]) -> None:
    """In-place simplify deepObject filter param schemas."""
    for path_item in spec.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for param in operation.get("parameters", []):
                if not isinstance(param, dict):
                    continue
                if param.get("style") != "deepObject":
                    continue
                schema = param.get("schema", {})
                all_of = schema.get("allOf")
                _expected_allof_len = 2
                if not isinstance(all_of, list) or len(all_of) != _expected_allof_len:
                    continue
                object_items = [item for item in all_of if isinstance(item, dict) and item.get("type") == "object"]
                if len(object_items) == 1:
                    param["schema"] = object_items[0]


def main() -> int:
    """Simplify the bundled spec and write to the output path."""
    _expected_argc = 3
    if len(sys.argv) != _expected_argc:
        sys.stderr.write(f"Usage: {sys.argv[0]} INPUT_SPEC OUTPUT_SPEC\n")
        return 1

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    spec = yaml.safe_load(input_path.read_text(encoding="utf-8"))
    _simplify_filter_params(spec)
    output_path.write_text(
        yaml.dump(spec, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    sys.stderr.write(f"Simplified spec written to {output_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
