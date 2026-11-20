"""Tests for generated client lazy-loading behavior."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from typing import TYPE_CHECKING, Any, cast

from orchestrator_cli import commands as commands_module

if TYPE_CHECKING:
    from pathlib import Path


def test_models_package_lazy_loads_requested_model() -> None:
    """The models package should load model modules on first attribute access."""
    models = importlib.import_module("syntara_api_client.models")

    group_create = models.GroupCreate

    assert group_create.__name__ == "GroupCreate"
    assert models.GroupCreate is group_create


def test_api_registry_imports_groups_package_on_demand() -> None:
    """Accessing the groups registry should import only that tag package."""
    for module_name in list(sys.modules):
        if module_name == "syntara_api_client.api" or module_name.startswith("syntara_api_client.api."):
            sys.modules.pop(module_name)

    api_module = importlib.import_module("syntara_api_client.api")

    assert "syntara_api_client.api.groups" not in sys.modules

    registry = api_module.SyntaraApiRegistry(client=cast("Any", object()))
    groups_api = registry.groups

    assert groups_api.__class__.__name__ == "GroupsApi"
    assert "syntara_api_client.api.groups" in sys.modules


def test_cli_can_scan_generated_endpoint_modules_without_importing_api_module(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The CLI should discover endpoint modules by scanning the package directory."""
    package_dir = tmp_path / "syntara_api_client"
    api_dir = package_dir / "api"
    groups_dir = api_dir / "groups"
    groups_dir.mkdir(parents=True)
    (api_dir / "__init__.py").write_text("")
    (groups_dir / "__init__.py").write_text("")
    (groups_dir / "create_group.py").write_text("")
    (groups_dir / "list_groups.py").write_text("")

    class DummySpec:
        submodule_search_locations = (str(package_dir),)

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: DummySpec() if name == "syntara_api_client" else None)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(AssertionError(f"unexpected import: {name}")),
    )

    discovered = commands_module._discover_endpoint_modules()

    assert discovered == {"groups": ["create_group", "list_groups"]}
