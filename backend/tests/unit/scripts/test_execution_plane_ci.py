"""Regression tests for execution-plane discovery in backend CI checks."""

from pathlib import Path

import pytest

from tools.ci import check_api_path_naming, check_orphan_modules, verify_test_structure


def test_orphan_check_resolves_imports_across_source_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main_src = tmp_path / "src"
    ep_src = tmp_path / "execution-plane" / "src"
    main_package = main_src / "syntara"
    ep_package = ep_src / "execution_plane"
    main_package.mkdir(parents=True)
    ep_package.mkdir(parents=True)
    (main_package / "api.py").write_text("from execution_plane.router import router\n")
    router = ep_package / "router.py"
    router.write_text("from syntara.authz import PermissionChecker\n")
    orphan = ep_package / "unused.py"
    orphan.write_text("value = 1\n")

    monkeypatch.setattr(check_orphan_modules, "SOURCE_ROOTS", (main_src, ep_src))
    monkeypatch.setattr(check_orphan_modules, "SYNTARA_DIR", main_package)
    monkeypatch.setattr(check_orphan_modules, "EP_SRC_DIR", ep_src)

    imports = check_orphan_modules.scan_imports()
    assert "execution_plane.router" in imports
    assert "syntara.authz" in imports
    assert "execution_plane.unused" not in imports
    assert orphan in check_orphan_modules.get_source_files()
    assert check_orphan_modules.file_to_module(router) == "execution_plane.router"


def test_api_path_check_inspects_execution_plane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ep_source = tmp_path / "execution-plane" / "src" / "execution_plane"
    ep_source.mkdir(parents=True)
    router = ep_source / "router.py"
    router.write_text('@router.get("/bad-path")\n')
    monkeypatch.setattr(check_api_path_naming, "ROOT", tmp_path)
    monkeypatch.setattr(check_api_path_naming, "SRC_DIR", tmp_path / "src" / "syntara")
    assert check_api_path_naming.main() == 1

    router.write_text('@router.get("/good_path")\n')
    assert check_api_path_naming.main() == 0


def test_execution_plane_test_structure_rejects_orphan_tests(tmp_path: Path) -> None:
    ep = tmp_path / "execution-plane"
    source = ep / "src" / "execution_plane"
    tests = ep / "tests"
    source.mkdir(parents=True)
    tests.mkdir()
    (tests / "test_executor.py").touch()
    success, errors, _ = verify_test_structure.verify_test_structure(tmp_path)
    assert not success
    assert any("test_executor.py" in error for error in errors)

    (source / "executor.py").touch()
    success, errors, _ = verify_test_structure.verify_test_structure(tmp_path)
    assert success, errors
