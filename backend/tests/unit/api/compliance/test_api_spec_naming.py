"""Ensure static OpenAPI specs use the upstream "Syntara" product name."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.export_openapi import build_spec_app

_SCHEMAS_DIR = Path(__file__).resolve().parents[4] / "src" / "syntara" / "schemas"


@pytest.fixture(scope="module")
def runtime_spec() -> dict[str, Any]:
    """Generate the runtime OpenAPI spec from the live FastAPI app."""
    app = build_spec_app()
    return app.openapi()


def _collect_strings(obj: dict[str, object] | list[object] | str | object, path: str = "") -> list[tuple[str, str]]:
    """Walk the spec and collect all string values with their JSON path."""
    results: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            results.extend(_collect_strings(key, f"{path}.<key>"))
            results.extend(_collect_strings(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            results.extend(_collect_strings(item, f"{path}[{i}]"))
    elif isinstance(obj, str):
        results.append((path, obj))
    return results


class TestStaticSpecNaming:
    """Verify static API specs retain the upstream product name."""

    def test_title_uses_syntara(self, runtime_spec: dict[str, Any]) -> None:
        """The static spec title must use Syntara."""
        title = runtime_spec.get("info", {}).get("title", "")
        assert title == "Syntara API", f"Spec title must be 'Syntara API': {title}"

    def test_no_downstream_product_name_in_spec(self, runtime_spec: dict[str, Any]) -> None:
        """Static specs must not contain the downstream product name."""
        spec_text = json.dumps(runtime_spec)
        if "Automation Orchestrator" not in spec_text:
            return
        violations = [
            f"{path}: {value}" for path, value in _collect_strings(runtime_spec) if "Automation Orchestrator" in value
        ]
        assert violations == [], "Downstream product name found in API spec:\n" + "\n".join(
            f"  {v}" for v in violations
        )


class TestStaticJsonSchemaNaming:
    """Verify static JSON schema files retain the upstream product name."""

    def test_no_downstream_product_name_in_json_schemas(self) -> None:
        """No JSON schema file should contain the downstream product name."""
        violations = []
        for path in sorted(_SCHEMAS_DIR.rglob("*.schema.json")):
            content = path.read_text(encoding="utf-8")
            if "Automation Orchestrator" in content:
                data = json.loads(content)
                rel = path.relative_to(_SCHEMAS_DIR)
                for json_path, value in _collect_strings(data):
                    if "Automation Orchestrator" in value:
                        violations.append(f"{rel}{json_path}: {value}")
        assert violations == [], "Downstream product name found in JSON schema files:\n" + "\n".join(
            f"  {v}" for v in violations
        )
