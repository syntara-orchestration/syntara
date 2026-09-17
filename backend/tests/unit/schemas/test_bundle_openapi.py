"""Unit tests for the bundle_openapi CLI tool's output-path selection."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from tools.bundle_openapi import DEFAULT_OUTPUT, DEFAULT_PUBLIC_OUTPUT, _default_output_path, _parse_args

if TYPE_CHECKING:
    import pytest


class TestFormatArgumentDefault:
    """--format defaults to yaml, preserving pre-existing behavior when omitted."""

    def test_format_defaults_to_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.argv", ["bundle_openapi.py"])
        args = _parse_args()
        assert args.format == "yaml"

    def test_format_accepts_json_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.argv", ["bundle_openapi.py", "--format", "json"])
        args = _parse_args()
        assert args.format == "json"


class TestDefaultOutputPath:
    """The default output path must match the requested --format, not always .yaml."""

    def test_yaml_format_full_spec(self) -> None:
        args = argparse.Namespace(public=False, format="yaml")
        assert _default_output_path(args) == DEFAULT_OUTPUT

    def test_yaml_format_public_spec(self) -> None:
        args = argparse.Namespace(public=True, format="yaml")
        assert _default_output_path(args) == DEFAULT_PUBLIC_OUTPUT

    def test_json_format_public_spec_uses_json_extension(self) -> None:
        """Regression test: --format json without -o must not write JSON into a .yaml-named file."""
        args = argparse.Namespace(public=True, format="json")
        result = _default_output_path(args)
        assert result.suffix == ".json"
        assert result == DEFAULT_PUBLIC_OUTPUT.with_suffix(".json")

    def test_json_format_full_spec_uses_json_extension(self) -> None:
        args = argparse.Namespace(public=False, format="json")
        result = _default_output_path(args)
        assert result.suffix == ".json"
        assert result == DEFAULT_OUTPUT.with_suffix(".json")
