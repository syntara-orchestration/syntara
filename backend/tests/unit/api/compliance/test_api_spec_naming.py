"""Ensure the OpenAPI spec uses "Orchestrator", not "Syntara"."""

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


class TestNoSyntaraInSpec:
    """Verify the API spec uses Orchestrator, not Syntara."""

    def test_title_uses_orchestrator(self, runtime_spec: dict[str, Any]) -> None:
        """The spec title must use Orchestrator, not Syntara."""
        title = runtime_spec.get("info", {}).get("title", "")
        assert "Syntara" not in title, f"Spec title contains 'Syntara': {title}"
        assert "Orchestrator" in title, f"Spec title missing 'Orchestrator': {title}"

    def test_no_syntara_in_spec(self, runtime_spec: dict[str, Any]) -> None:
        """No string value in the spec should contain 'Syntara'."""
        spec_text = json.dumps(runtime_spec)
        if "Syntara" not in spec_text:
            return
        violations = [f"{path}: {value}" for path, value in _collect_strings(runtime_spec) if "Syntara" in value]
        assert violations == [], "Project name 'Syntara' found in API spec:\n" + "\n".join(f"  {v}" for v in violations)


class TestNoSyntaraInJsonSchemas:
    """Verify static JSON schema files use Orchestrator, not Syntara."""

    def test_no_syntara_in_json_schemas(self) -> None:
        """No JSON schema file should contain 'Syntara'."""
        violations = []
        for path in sorted(_SCHEMAS_DIR.rglob("*.schema.json")):
            content = path.read_text(encoding="utf-8")
            if "Syntara" in content:
                data = json.loads(content)
                rel = path.relative_to(_SCHEMAS_DIR)
                for json_path, value in _collect_strings(data):
                    if "Syntara" in value:
                        violations.append(f"{rel}{json_path}: {value}")
        assert violations == [], "Project name 'Syntara' found in JSON schema files:\n" + "\n".join(
            f"  {v}" for v in violations
        )
