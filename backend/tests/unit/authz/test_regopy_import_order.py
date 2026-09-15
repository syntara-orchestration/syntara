"""Regression tests for the regopy preload in ``syntara/__init__.py``.

``librego_shared.so`` (rego-cpp) statically links snmalloc and exports
``operator new``/``operator delete``.  When another native library (greenlet,
temporalio's Rust bridge) loads first, libstdc++ allocation symbols bind
across two allocators and every rego query permanently leaks ~69 KB of native
memory — enough to OOM the backend under E2E load.  ``syntara/__init__.py``
therefore imports regopy before anything else, guarded so environments that
cannot load it (no regopy installed, or UBI images without libatomic.so.1)
still import cleanly.

Each scenario runs in a subprocess so it observes a pristine interpreter.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_UBI_LOADER_ERROR = "libatomic.so.1: cannot open shared object file: No such file or directory"


def _run_python(code: str, *, extra_pythonpath: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run *code* in a fresh interpreter, optionally shadowing modules via PYTHONPATH."""
    env = os.environ.copy()
    if extra_pythonpath is not None:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(extra_pythonpath) + (os.pathsep + existing if existing else "")
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )


def test_import_syntara_preloads_regopy_before_greenlet():
    """``import syntara`` must load regopy before greenlet can claim the allocator."""
    pytest.importorskip("regopy")
    result = _run_python(
        """
        import sys

        import syntara

        assert "regopy" in sys.modules, "import syntara did not preload regopy"
        assert syntara._REGOPY_PRELOAD_ERROR is None

        import greenlet  # noqa: F401

        modules = list(sys.modules)
        assert modules.index("regopy") < modules.index("greenlet"), (
            "regopy must be inserted into sys.modules before greenlet"
        )
        print("ORDER-OK")
        """
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "ORDER-OK" in result.stdout


def test_missing_libatomic_is_tolerated_and_recorded(tmp_path):
    """The known UBI loader gap (PR #560) must not break ``import syntara``."""
    (tmp_path / "regopy.py").write_text(f'raise OSError("{_UBI_LOADER_ERROR}")\n')
    result = _run_python(
        """
        import syntara

        assert syntara._REGOPY_PRELOAD_ERROR is not None
        assert "cannot open shared object file" in syntara._REGOPY_PRELOAD_ERROR
        print("SENTINEL-OK")
        """,
        extra_pythonpath=tmp_path,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "SENTINEL-OK" in result.stdout


def test_regopy_not_installed_is_tolerated_and_recorded(tmp_path):
    """A missing regopy distribution (collection-only envs) must be tolerated.

    The import machinery raises ``ModuleNotFoundError`` with ``name="regopy"``
    when the distribution is absent; the stub replicates that exactly.
    """
    (tmp_path / "regopy.py").write_text('raise ModuleNotFoundError("No module named \'regopy\'", name="regopy")\n')
    result = _run_python(
        """
        import syntara

        assert syntara._REGOPY_PRELOAD_ERROR is not None
        print("SENTINEL-OK")
        """,
        extra_pythonpath=tmp_path,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "SENTINEL-OK" in result.stdout


def test_missing_transitive_dependency_is_raised(tmp_path):
    """A ModuleNotFoundError for anything other than regopy itself must surface.

    A missing transitive dependency of regopy is a packaging fault, not the
    documented collection-only gap — the preload must not swallow it.
    """
    (tmp_path / "regopy.py").write_text('raise ModuleNotFoundError("No module named \'cffi\'", name="cffi")\n')
    result = _run_python(
        """
        import syntara  # noqa: F401
        print("SHOULD-NOT-REACH")
        """,
        extra_pythonpath=tmp_path,
    )
    assert result.returncode != 0
    assert "SHOULD-NOT-REACH" not in result.stdout
    assert "No module named 'cffi'" in result.stderr


def test_other_missing_shared_object_is_raised(tmp_path):
    """An unloadable shared object other than libatomic.so.1 must surface."""
    (tmp_path / "regopy.py").write_text(
        'raise OSError("libfoo.so.3: cannot open shared object file: No such file or directory")\n'
    )
    result = _run_python(
        """
        import syntara  # noqa: F401
        print("SHOULD-NOT-REACH")
        """,
        extra_pythonpath=tmp_path,
    )
    assert result.returncode != 0
    assert "SHOULD-NOT-REACH" not in result.stdout
    assert "libfoo.so.3" in result.stderr


def test_unexpected_regopy_import_error_is_raised(tmp_path):
    """Anything other than the known loader gaps must surface immediately."""
    (tmp_path / "regopy.py").write_text('raise ImportError("unexpected loader explosion")\n')
    result = _run_python(
        """
        import syntara  # noqa: F401
        print("SHOULD-NOT-REACH")
        """,
        extra_pythonpath=tmp_path,
    )
    assert result.returncode != 0
    assert "SHOULD-NOT-REACH" not in result.stdout
    assert "unexpected loader explosion" in result.stderr


def test_tripwire_warns_when_greenlet_precedes_regopy():
    """The startup tripwire must fire when greenlet claimed the allocator first."""
    pytest.importorskip("regopy")
    result = _run_python(
        """
        import greenlet  # noqa: F401  # simulates an entrypoint bypassing the preload

        from syntara.authz import evaluator

        evaluator._warn_if_import_order_regressed()
        """
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "imported before regopy" in result.stdout + result.stderr
    assert "greenlet" in result.stdout + result.stderr


def test_tripwire_warns_when_temporalio_bridge_precedes_regopy():
    """The tripwire must also fire for temporalio's Rust bridge (same leak)."""
    pytest.importorskip("regopy")
    pytest.importorskip("temporalio")
    result = _run_python(
        """
        import temporalio.bridge.temporal_sdk_bridge  # noqa: F401

        from syntara.authz import evaluator

        evaluator._warn_if_import_order_regressed()
        """
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "imported before regopy" in result.stdout + result.stderr
    assert "temporal_sdk_bridge" in result.stdout + result.stderr


def test_tripwire_silent_when_preload_order_is_correct():
    """With the package preload intact, the tripwire must stay silent."""
    pytest.importorskip("regopy")
    pytest.importorskip("temporalio")
    result = _run_python(
        """
        from syntara.authz import evaluator  # syntara preloads regopy first

        import greenlet  # noqa: F401
        import temporalio.bridge.temporal_sdk_bridge  # noqa: F401

        evaluator._warn_if_import_order_regressed()
        """
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "imported before regopy" not in result.stdout + result.stderr
