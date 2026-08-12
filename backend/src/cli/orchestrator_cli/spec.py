"""OpenAPI spec management — auto-bundle and cache in ``~/.orchestrator/``.

On CLI startup, this module locates the project's schema sources,
hashes them, and re-bundles the OpenAPI spec only when sources have
changed. The cache is stored as JSON for fast warm-start parsing, with
legacy YAML caches still supported as a fallback.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.machinery
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from .benchmark import note, phase

_log = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".orchestrator"
_CACHED_SPEC_JSON = _CONFIG_DIR / "openapi.json"
_LEGACY_CACHED_SPEC_YAML = _CONFIG_DIR / "openapi.yaml"
_HASH_MANIFEST = _CONFIG_DIR / "spec-hashes.json"

# ---------------------------------------------------------------------------
# Project root / schemas discovery
# ---------------------------------------------------------------------------

_SCHEMAS_RELATIVE = Path("src") / "syntara" / "schemas"


def _find_project_root() -> Path | None:
    """Walk up from the cli package until we find the project root."""
    candidate = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / _SCHEMAS_RELATIVE).is_dir():
            return candidate
    return None


def _find_schemas_dir() -> Path | None:
    root = _find_project_root()
    if root is None:
        return None
    schemas = root / _SCHEMAS_RELATIVE
    return schemas if schemas.is_dir() else None


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _collect_source_files(schemas_dir: Path) -> list[Path]:
    """Return all YAML/JSON files under the schemas directory, sorted for determinism."""
    files: list[Path] = []
    for pattern in ("**/*.yaml", "**/*.yml", "**/*.json"):
        files.extend(schemas_dir.glob(pattern))
    return sorted(set(files))


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_manifest(source_files: list[Path], schemas_dir: Path) -> dict[str, str]:
    """Return {relative_path: sha256_hex} for each source file."""
    return {str(f.relative_to(schemas_dir)): _hash_file(f) for f in source_files}


def _load_saved_manifest() -> dict[str, str] | None:
    with phase("spec.load_saved_manifest"):
        if not _HASH_MANIFEST.exists():
            return None
        try:
            result: dict[str, str] = json.loads(_HASH_MANIFEST.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return result


def _save_manifest(manifest: dict[str, str]) -> None:
    with phase("spec.save_manifest"):
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _HASH_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Bundling
# ---------------------------------------------------------------------------


def _bundle_spec(schemas_dir: Path) -> dict[str, Any]:
    """Run the project's bundle_openapi logic to produce a merged spec dict.

    Tries to import the bundler from the project.  If unavailable, falls
    back to reading the already-bundled ``openapi.yaml`` in the schemas dir.
    """
    with phase("spec.bundle_spec"):
        bundled_path = schemas_dir / "openapi.yaml"

        project_root = schemas_dir.parent.parent
        tools_dir = project_root / "tools"
        bundler_path = tools_dir / "bundle_openapi.py"

        if bundler_path.exists():
            sys.path.insert(0, str(tools_dir))
            try:
                loader = importlib.machinery.SourceFileLoader("_bundle_openapi", str(bundler_path))
                spec_obj = importlib.util.spec_from_loader("_bundle_openapi", loader)
                if spec_obj is not None and spec_obj.loader is not None:
                    mod = importlib.util.module_from_spec(spec_obj)
                    mod_name = "python_bundler"
                    spec_obj.loader.exec_module(mod)
                    sub_specs = mod._discover_sub_specs()
                    if sub_specs:
                        result: dict[str, Any] = mod._build_merged_spec(sub_specs)
                        note("spec_source", mod_name)
                        return result
            except (ImportError, AttributeError, yaml.YAMLError, OSError):
                _log.debug("Failed to run bundler, falling back to pre-bundled spec", exc_info=True)
            finally:
                if str(tools_dir) in sys.path:
                    sys.path.remove(str(tools_dir))

        if bundled_path.exists():
            note("spec_source", "bundled_yaml")
            with bundled_path.open("rb") as f:
                spec: dict[str, Any] = yaml.safe_load(f)
                return spec

        msg = f"No OpenAPI spec sources found under {schemas_dir}"
        raise FileNotFoundError(msg)


def _save_cached_spec(spec: dict[str, Any]) -> None:
    with phase("spec.save_cached_spec"):
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _CACHED_SPEC_JSON.write_text(
            json.dumps(spec, ensure_ascii=False, separators=(",", ":")),
        )


def _load_json_spec(path: Path) -> dict[str, Any]:
    with phase("spec.load_cached_spec.json"):
        spec: dict[str, Any] = json.loads(path.read_bytes())
        return spec


def _load_yaml_spec(path: Path) -> dict[str, Any]:
    with phase("spec.load_cached_spec.yaml"):
        with path.open("rb") as f:
            spec: dict[str, Any] = yaml.safe_load(f)
        return spec


def _load_cached_spec() -> dict[str, Any] | None:
    if _CACHED_SPEC_JSON.exists():
        try:
            note("spec_cache", "json")
            return _load_json_spec(_CACHED_SPEC_JSON)
        except (json.JSONDecodeError, OSError, yaml.YAMLError):
            _log.debug("Failed to load cached spec", extra={"path": str(_CACHED_SPEC_JSON)}, exc_info=True)

    if _LEGACY_CACHED_SPEC_YAML.exists():
        try:
            note("spec_cache", "yaml")
            legacy_spec = _load_yaml_spec(_LEGACY_CACHED_SPEC_YAML)
        except (json.JSONDecodeError, OSError, yaml.YAMLError):
            _log.debug(
                "Failed to load cached spec",
                extra={"path": str(_LEGACY_CACHED_SPEC_YAML)},
                exc_info=True,
            )
        else:
            _save_cached_spec(legacy_spec)
            return legacy_spec

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_spec() -> dict[str, Any]:
    """Load the OpenAPI spec, re-bundling from sources if anything changed.

    Resolution order:
    1. Find the schemas dir in the project tree.
    2. Hash all source files and compare against the saved manifest.
    3. If hashes match and a cached spec exists, load from cache.
    4. Otherwise, re-bundle, save the spec and the new manifest.
    5. If no schemas dir is found (e.g. pip-installed outside the project),
       fall back to the cached spec or the in-package copy.
    """
    with phase("spec.load_spec"):
        with phase("spec.find_schemas_dir"):
            schemas_dir = _find_schemas_dir()

        if schemas_dir is not None:
            with phase("spec.collect_source_files"):
                source_files = _collect_source_files(schemas_dir)
            note("spec_source_file_count", len(source_files))
            with phase("spec.build_manifest"):
                current_manifest = _build_manifest(source_files, schemas_dir)
            saved_manifest = _load_saved_manifest()

            if current_manifest == saved_manifest:
                cached = _load_cached_spec()
                if cached is not None:
                    return cached

            note("spec_cache", "rebuild")
            spec = _bundle_spec(schemas_dir)
            _save_cached_spec(spec)
            _save_manifest(current_manifest)
            return spec

        cached_fallback = _load_cached_spec()
        if cached_fallback is not None:
            return cached_fallback

        package_spec = Path(__file__).resolve().parent / "openapi.yaml"
        if package_spec.exists():
            note("spec_source", "package_openapi_yaml")
            with phase("spec.load_package_fallback"), package_spec.open("rb") as f:
                pkg_spec: dict[str, Any] = yaml.safe_load(f)
                return pkg_spec

        msg = (
            "Cannot find OpenAPI spec: no schemas directory, no cached spec, "
            "and no bundled openapi.yaml in the orchestrator_cli package. "
            "Run 'make api-spec-bundle' to generate the spec."
        )
        raise FileNotFoundError(msg)
