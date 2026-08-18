"""Ensure the public-facing OpenAPI spec contains no internal endpoints.

The public spec (openapi-public.yaml) is served at runtime and must never
expose /_internal/* paths, Internal Metrics tags, or schemas used only by
internal endpoints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

_SCHEMAS_DIR = Path(__file__).resolve().parents[4] / "src" / "syntara" / "schemas"
_PUBLIC_SPEC_PATH = _SCHEMAS_DIR / "openapi-public.yaml"


@pytest.fixture(scope="module")
def public_spec() -> dict[str, Any]:
    if not _PUBLIC_SPEC_PATH.exists():
        pytest.skip(f"Public spec not found at {_PUBLIC_SPEC_PATH}")
    spec: dict[str, Any] = yaml.safe_load(_PUBLIC_SPEC_PATH.read_text(encoding="utf-8"))
    return spec


class TestNoInternalPaths:
    """Verify no /_internal/ paths leak into the public spec."""

    def test_no_internal_path_prefix(self, public_spec: dict[str, Any]) -> None:
        """No path should start with /_internal/."""
        internal_paths = [p for p in public_spec.get("paths", {}) if p.startswith("/_internal/")]
        assert internal_paths == [], f"Internal paths leaked into public spec: {internal_paths}"

    def test_no_internal_path_anywhere(self, public_spec: dict[str, Any]) -> None:
        """No path should contain '/_internal/' at any position."""
        internal_paths = [p for p in public_spec.get("paths", {}) if "/_internal/" in p]
        assert internal_paths == [], f"Paths containing /_internal/: {internal_paths}"


class TestNoInternalTags:
    """Verify no internal tags appear on any operation."""

    def test_no_internal_metrics_tag_in_tags_list(self, public_spec: dict[str, Any]) -> None:
        """The top-level tags list must not include 'Internal Metrics'."""
        tag_names = [t.get("name", "") for t in public_spec.get("tags", [])]
        assert "Internal Metrics" not in tag_names

    def test_no_internal_tag_on_any_operation(self, public_spec: dict[str, Any]) -> None:
        """No operation should be tagged with any tag containing 'Internal'."""
        violations = []
        for path, path_item in public_spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if not isinstance(operation, dict):
                    continue
                for tag in operation.get("tags", []):
                    if "internal" in tag.lower():
                        violations.append(f"{method.upper()} {path} tagged '{tag}'")
        assert violations == [], f"Operations with internal tags: {violations}"


class TestNoInternalSchemas:
    """Verify schemas exclusive to internal endpoints are absent."""

    _INTERNAL_ONLY_SCHEMAS: ClassVar[set[str]] = {
        "MetricsStoreSummary",
        "MetricsRecordPage",
        "MetricRecord",
        "MetricType",
        "MetricsCategoryType",
        "KPIDashboard",
        "ComponentKPISummary",
        "PercentileStats",
    }

    def test_no_internal_only_schemas(self, public_spec: dict[str, Any]) -> None:
        """Schemas used exclusively by internal endpoints must not appear."""
        schemas = set(public_spec.get("components", {}).get("schemas", {}).keys())
        leaked = schemas & self._INTERNAL_ONLY_SCHEMAS
        assert leaked == set(), f"Internal-only schemas in public spec: {leaked}"


class TestNoInternalOperationIds:
    """Verify no operationId references internal endpoints."""

    def test_no_internal_operation_ids(self, public_spec: dict[str, Any]) -> None:
        """No operationId should reference internal endpoints."""
        violations = []
        for path, path_item in public_spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if not isinstance(operation, dict):
                    continue
                op_id = operation.get("operationId", "")
                if "internal" in op_id.lower():
                    violations.append(f"{method.upper()} {path}: {op_id}")
        assert violations == [], f"Internal operationIds in public spec: {violations}"


class TestPublicSpecIsValid:
    """Basic structural validation of the public spec."""

    def test_has_openapi_version(self, public_spec: dict[str, Any]) -> None:
        assert public_spec.get("openapi") == "3.1.0"

    def test_has_info(self, public_spec: dict[str, Any]) -> None:
        assert "info" in public_spec
        assert "title" in public_spec["info"]
        assert "version" in public_spec["info"]

    def test_has_paths(self, public_spec: dict[str, Any]) -> None:
        assert "paths" in public_spec
        assert len(public_spec["paths"]) > 0, "Public spec has no paths"

    def test_has_components(self, public_spec: dict[str, Any]) -> None:
        assert "components" in public_spec

    def test_full_spec_has_more_paths(self) -> None:
        """The full spec must have strictly more paths than the public spec."""
        full_path = _SCHEMAS_DIR / "openapi.yaml"
        if not full_path.exists() or not _PUBLIC_SPEC_PATH.exists():
            pytest.skip("Both specs required for comparison")
        full_spec = yaml.safe_load(full_path.read_text(encoding="utf-8"))
        public_spec = yaml.safe_load(_PUBLIC_SPEC_PATH.read_text(encoding="utf-8"))
        full_paths = set(full_spec.get("paths", {}).keys())
        public_paths = set(public_spec.get("paths", {}).keys())
        assert full_paths > public_paths, (
            f"Full spec should be a strict superset of public spec paths. Only in public: {public_paths - full_paths}"
        )
