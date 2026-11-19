"""Keep the Git client dependency usable in offline build preparation."""

import io
import os
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[4]


def test_split_vcs_requirements_keeps_hashed_packages_separate(tmp_path):
    requirements = tmp_path / "requirements.txt"
    git = "execution-plane-client @ git+https://github.com/example/ep.git@" + "a" * 40 + "#subdirectory=src/client"
    requirements.write_text(f"# generated\n{git}\n    # via syntara\npydantic==2.12.0 \\\n    --hash=sha256:abc\n")
    result = subprocess.run(  # noqa: S603 - Run repository scripts with controlled test inputs.
        [sys.executable, str(BACKEND / "tools/ci/split_vcs_requirements.py"), str(requirements)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "git+" not in requirements.read_text()
    assert "--hash=sha256:abc" in requirements.read_text()
    vcs = (tmp_path / "requirements-vcs.txt").read_text()
    assert git in vcs
    assert "--hash" not in vcs


@pytest.mark.parametrize("reference", ['rev="main"', 'tag="v0.1.0"'])
def test_hermetic_source_uses_prefetched_client_subdirectory(tmp_path, reference):
    commit = "a" * 40
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname="ao"\nversion="0.1.0"\ndependencies=["execution-plane-client"]\n'
        "[tool.uv.sources]\n"
        'execution-plane-client = {git="https://github.com/example/ep.git", '
        f'{reference}, subdirectory="src/client"}}\n'
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname="execution-plane-client"\nversion="0.1.0"\n'
        f'source = {{git="https://github.com/example/ep.git?subdirectory=src%2Fclient#{commit}"}}\n'
    )
    archives = tmp_path / "archives"
    archives.mkdir()
    with tarfile.open(archives / f"ep-gitcommit-{commit}.tar.gz", "w:gz") as archive:
        info = tarfile.TarInfo("app/src/client/pyproject.toml")
        content = b'[project]\nname="execution-plane-client"\nversion="0.1.0"\n'
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    result = subprocess.run(  # noqa: S603 - Run repository scripts with controlled test inputs.
        [sys.executable, str(BACKEND / "tools/ci/sanitize_pyproject_for_hermetic.py"), str(pyproject)],
        env={**os.environ, "PIP_FIND_LINKS": str(archives)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    source = tomllib.loads(pyproject.read_text())["tool"]["uv"]["sources"]["execution-plane-client"]
    assert "git" not in source
    extracted = Path(source["path"]) / "pyproject.toml"
    assert tomllib.loads(extracted.read_text())["project"]["name"] == "execution-plane-client"
