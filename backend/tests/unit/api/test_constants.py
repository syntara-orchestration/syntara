"""Tests for API constants — single source of truth for version, paths, etc."""

from __future__ import annotations

from pathlib import Path

import yaml

SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "src" / "syntara" / "schemas"


class TestAPIVersionConstant:
    """API version is defined once in constants and used consistently."""

    def test_version_constant_exists(self) -> None:
        """API_V1_VERSION is importable and non-empty."""
        from syntara.api.constants import API_V1_VERSION

        assert isinstance(API_V1_VERSION, str)
        assert len(API_V1_VERSION) > 0

    def test_app_version_matches_constant(self) -> None:
        """FastAPI app.version is wired to the shared constant."""
        from syntara.api.constants import API_V1_VERSION
        from syntara.api.main import app as real_app

        assert real_app.version == API_V1_VERSION

    def test_export_openapi_version_matches_constant(self) -> None:
        """export_openapi build_spec_app uses the shared constant."""
        from syntara.api.constants import API_V1_VERSION
        from tools.export_openapi import build_spec_app

        spec_app = build_spec_app()
        assert spec_app.version == API_V1_VERSION

    def test_bundled_openapi_spec_version_matches_constant(self) -> None:
        """Generated openapi.yaml info.version stays in sync with the constant."""
        from syntara.api.constants import API_V1_VERSION

        spec_path = SCHEMAS_DIR / "openapi.yaml"
        spec = yaml.safe_load(spec_path.read_text())
        assert spec["info"]["version"] == API_V1_VERSION
