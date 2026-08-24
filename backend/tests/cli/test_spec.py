"""Tests for CLI spec caching behavior."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest
from orchestrator_cli import spec as spec_module

if TYPE_CHECKING:
    from pathlib import Path


def test_load_spec_prefers_json_cache_when_manifest_matches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The JSON cache should win when the source manifest still matches."""
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()

    cached_json = tmp_path / "openapi.json"
    legacy_yaml = tmp_path / "openapi.yaml"
    manifest_path = tmp_path / "spec-hashes.json"

    json_spec = {"openapi": "3.1.0", "info": {"title": "json-cache"}}
    cached_json.write_text(json.dumps(json_spec))
    legacy_yaml.write_text("openapi: 3.1.0\ninfo:\n  title: yaml-cache\n")
    manifest_path.write_text(json.dumps({"users/openapi.yaml": "abc"}))

    monkeypatch.setattr(spec_module, "_CACHED_SPEC_JSON", cached_json)
    monkeypatch.setattr(spec_module, "_LEGACY_CACHED_SPEC_YAML", legacy_yaml)
    monkeypatch.setattr(spec_module, "_HASH_MANIFEST", manifest_path)
    monkeypatch.setattr(spec_module, "_find_schemas_dir", lambda: schemas_dir)
    monkeypatch.setattr(spec_module, "_collect_source_files", lambda _: [schemas_dir / "users.openapi.yaml"])
    monkeypatch.setattr(spec_module, "_build_manifest", lambda *_: {"users/openapi.yaml": "abc"})

    spec = spec_module.load_spec()

    assert spec == json_spec


def test_load_spec_falls_back_to_legacy_yaml_cache_when_json_cache_is_invalid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """An invalid JSON cache should fall back to legacy YAML and rewrite JSON."""
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()

    cached_json = tmp_path / "openapi.json"
    legacy_yaml = tmp_path / "openapi.yaml"
    manifest_path = tmp_path / "spec-hashes.json"

    cached_json.write_text("{not valid json")
    legacy_yaml.write_text("openapi: 3.1.0\ninfo:\n  title: yaml-cache\n")
    manifest_path.write_text(json.dumps({"users/openapi.yaml": "abc"}))

    monkeypatch.setattr(spec_module, "_CACHED_SPEC_JSON", cached_json)
    monkeypatch.setattr(spec_module, "_LEGACY_CACHED_SPEC_YAML", legacy_yaml)
    monkeypatch.setattr(spec_module, "_HASH_MANIFEST", manifest_path)
    monkeypatch.setattr(spec_module, "_find_schemas_dir", lambda: schemas_dir)
    monkeypatch.setattr(spec_module, "_collect_source_files", lambda _: [schemas_dir / "users.openapi.yaml"])
    monkeypatch.setattr(spec_module, "_build_manifest", lambda *_: {"users/openapi.yaml": "abc"})

    spec = spec_module.load_spec()

    assert spec["info"]["title"] == "yaml-cache"
    assert json.loads(cached_json.read_text())["info"]["title"] == "yaml-cache"


def test_load_spec_falls_back_to_bundled_package_yaml_when_no_source_tree_or_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Bundled openapi.yaml fallback when no source tree or cache exists.

    Regression test: the previous fallback looked inside the syntara_api_client package directory,
    which does not ship openapi.yaml, causing a FileNotFoundError on every import of
    orchestrator_cli outside the source tree.

    Uses a fake package dir (not the source-tree sibling) so this proves Path(__file__).parent
    lookup the way an installed wheel would resolve it.
    """
    package_dir = tmp_path / "orchestrator_cli"
    package_dir.mkdir()
    bundled = package_dir / "openapi.yaml"
    bundled.write_text("openapi: 3.1.0\ninfo:\n  title: bundled-package-spec\n  version: '0.0.0'\npaths: {}\n")

    monkeypatch.setattr(spec_module, "_CACHED_SPEC_JSON", tmp_path / "openapi.json")
    monkeypatch.setattr(spec_module, "_LEGACY_CACHED_SPEC_YAML", tmp_path / "legacy-openapi.yaml")
    monkeypatch.setattr(spec_module, "_HASH_MANIFEST", tmp_path / "spec-hashes.json")
    monkeypatch.setattr(spec_module, "_find_schemas_dir", lambda: None)
    monkeypatch.setattr(spec_module, "__file__", str(package_dir / "spec.py"))

    spec = spec_module.load_spec()

    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"] == "bundled-package-spec"


def test_load_spec_raises_when_no_spec_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """FileNotFoundError should be raised with guidance when all fallbacks fail."""
    monkeypatch.setattr(spec_module, "_CACHED_SPEC_JSON", tmp_path / "openapi.json")
    monkeypatch.setattr(spec_module, "_LEGACY_CACHED_SPEC_YAML", tmp_path / "openapi.yaml")
    monkeypatch.setattr(spec_module, "_HASH_MANIFEST", tmp_path / "spec-hashes.json")
    monkeypatch.setattr(spec_module, "_find_schemas_dir", lambda: None)
    monkeypatch.setattr(spec_module, "__file__", str(tmp_path / "spec.py"))

    with pytest.raises(FileNotFoundError, match="orchestrator_cli"):
        spec_module.load_spec()


# ---------------------------------------------------------------------------
# _collect_source_files
# ---------------------------------------------------------------------------


def test_collect_source_files_returns_sorted_deduplicated_schema_files(
    tmp_path: Path,
) -> None:
    """Only yaml/yml/json files are collected; result is sorted and deduplicated."""
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "b.yaml").write_text("b: 1")
    (schemas_dir / "a.json").write_text("{}")
    (schemas_dir / "c.yml").write_text("c: 1")
    (schemas_dir / "ignored.txt").write_text("not a schema")

    files = spec_module._collect_source_files(schemas_dir)
    names = [f.name for f in files]

    assert "ignored.txt" not in names
    assert names == sorted(names)
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# _build_manifest
# ---------------------------------------------------------------------------


def test_build_manifest_maps_relative_paths_to_sha256(tmp_path: Path) -> None:
    """Each entry is relative to schemas_dir and its value is the file's sha256 hex digest."""
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    f = schemas_dir / "openapi.yaml"
    f.write_text("openapi: 3.1.0")

    manifest = spec_module._build_manifest([f], schemas_dir)

    assert list(manifest.keys()) == ["openapi.yaml"]
    expected_hash = hashlib.sha256(f.read_bytes()).hexdigest()
    assert manifest["openapi.yaml"] == expected_hash


# ---------------------------------------------------------------------------
# _bundle_spec fallback (E5)
# ---------------------------------------------------------------------------


def test_bundle_spec_falls_back_to_openapi_yaml_when_bundler_missing(
    tmp_path: Path,
) -> None:
    """When bundle_openapi.py does not exist, falls back to the pre-bundled openapi.yaml."""
    # Use a path structure where tools/bundle_openapi.py definitely does not exist
    schemas_dir = tmp_path / "project" / "src" / "syntara" / "schemas"
    schemas_dir.mkdir(parents=True)
    (schemas_dir / "openapi.yaml").write_text("openapi: 3.1.0\ninfo:\n  title: pre-bundled\n")

    result = spec_module._bundle_spec(schemas_dir)

    assert result["info"]["title"] == "pre-bundled"


# ---------------------------------------------------------------------------
# _load_cached_spec YAML → JSON migration (E6)
# ---------------------------------------------------------------------------


def test_load_cached_spec_migrates_legacy_yaml_to_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When only a legacy YAML cache exists, it is loaded and re-saved as JSON."""
    cached_json = tmp_path / "openapi.json"
    legacy_yaml = tmp_path / "openapi.yaml"
    legacy_yaml.write_text("openapi: 3.1.0\ninfo:\n  title: migrated\n")

    monkeypatch.setattr(spec_module, "_CACHED_SPEC_JSON", cached_json)
    monkeypatch.setattr(spec_module, "_LEGACY_CACHED_SPEC_YAML", legacy_yaml)
    monkeypatch.setattr(spec_module, "_CONFIG_DIR", tmp_path)

    spec = spec_module._load_cached_spec()

    assert spec is not None
    assert spec["info"]["title"] == "migrated"
    assert cached_json.exists()
    assert json.loads(cached_json.read_text())["info"]["title"] == "migrated"


# ---------------------------------------------------------------------------
# _save_manifest
# ---------------------------------------------------------------------------


def test_save_manifest_writes_pretty_sorted_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manifest keys are sorted so diffs are stable regardless of insertion order."""
    manifest_path = tmp_path / "spec-hashes.json"
    monkeypatch.setattr(spec_module, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(spec_module, "_HASH_MANIFEST", manifest_path)

    spec_module._save_manifest({"b_file.yaml": "222", "a_file.yaml": "111"})

    data = json.loads(manifest_path.read_text())
    assert list(data.keys()) == ["a_file.yaml", "b_file.yaml"]


# ---------------------------------------------------------------------------
# load_spec re-bundles when manifest changes (E1 + E2)
# ---------------------------------------------------------------------------


def test_load_spec_rebundles_and_updates_cache_when_manifest_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When source hashes differ from the saved manifest, the spec is re-bundled.

    Both the JSON cache and the manifest file are updated on a hash mismatch.
    """
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()

    cached_json = tmp_path / "openapi.json"
    manifest_path = tmp_path / "spec-hashes.json"
    manifest_path.write_text(json.dumps({"old.yaml": "old-hash"}))

    new_spec = {"openapi": "3.1.0", "info": {"title": "rebundled"}}

    monkeypatch.setattr(spec_module, "_CACHED_SPEC_JSON", cached_json)
    monkeypatch.setattr(spec_module, "_LEGACY_CACHED_SPEC_YAML", tmp_path / "legacy.yaml")
    monkeypatch.setattr(spec_module, "_HASH_MANIFEST", manifest_path)
    monkeypatch.setattr(spec_module, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(spec_module, "_find_schemas_dir", lambda: schemas_dir)
    monkeypatch.setattr(spec_module, "_collect_source_files", lambda _: [])
    monkeypatch.setattr(spec_module, "_build_manifest", lambda *_: {"new.yaml": "new-hash"})
    monkeypatch.setattr(spec_module, "_bundle_spec", lambda _: new_spec)

    spec = spec_module.load_spec()

    assert spec["info"]["title"] == "rebundled"
    assert json.loads(cached_json.read_text())["info"]["title"] == "rebundled"
    assert json.loads(manifest_path.read_text()) == {"new.yaml": "new-hash"}
