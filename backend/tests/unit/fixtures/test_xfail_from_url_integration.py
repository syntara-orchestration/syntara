"""End-to-end integration tests for the ``--xfail-from-url`` pytest plugin.

Unlike the pure-logic tests in ``test_xfail_from_url.py``, these run a *real*
pytest session in a subprocess with the plugin loaded and a generated Markdown
xfail list, then assert on the actual outcome (return code and xfail/pass/fail
counts). This validates the whole mechanism end to end: collection, pattern
matching (including parametrized ids matched by base id), and the applied
``xfail`` marker.

They live under ``tests/unit/`` (not ``tests/integration/``) on purpose: the
integration tree has autouse fixtures that require the database/container
runtime, which this subprocess-based test does not need. The subprocess itself
is the integration boundary, so it runs in the fast unit job with no infra.

Isolation: ``PYTEST_DISABLE_PLUGIN_AUTOLOAD`` stops the backend conftest /
test-sdk plugins from loading in the child, a throwaway ``pytest.ini`` fixes the
rootdir to the temp dir, and only ``tests.fixtures.xfail_from_url`` is loaded
explicitly via ``-p``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# tests/unit/fixtures/test_xfail_from_url_integration.py -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _run_pytest(
    tmp_path: Path,
    *,
    test_src: str,
    md_src: str | None,
    extra_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Run pytest over *test_src* in an isolated subprocess, optionally with an xfail list."""
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts =\n")
    (tmp_path / "test_sample.py").write_text(test_src)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(tmp_path),
        "-p",
        "tests.fixtures.xfail_from_url",
        "-p",
        "no:cacheprovider",
        "-q",
        *extra_args,
    ]
    if md_src is not None:
        md = tmp_path / "xfail.md"
        md.write_text(md_src)
        cmd += ["--xfail-from-url", str(md)]

    env = {
        **os.environ,
        "PYTHONPATH": str(_BACKEND_ROOT),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    return subprocess.run(cmd, cwd=tmp_path, env=env, capture_output=True, text=True, check=False)  # noqa: S603


def _count(output: str, word: str) -> int:
    """Extract the ``<n> <word>`` count from pytest's summary line (0 if absent)."""
    match = re.search(rf"(\d+) {word}", output)
    return int(match.group(1)) if match else 0


class TestXfailFromUrlIntegration:
    """Run the plugin in a real (sub)pytest session and assert on the outcome."""

    def test_listed_failures_are_xfailed_and_suite_passes(self, tmp_path: Path) -> None:
        test_src = (
            "import pytest\n\n"
            '@pytest.mark.parametrize("case", ["a", "b"])\n'
            "def test_param(case):\n"
            "    assert False\n\n"
            "def test_plain_fail():\n"
            "    assert False\n\n"
            "def test_control_pass():\n"
            "    assert True\n"
        )
        md_src = "# test_sample.py::test_param\nflaky param\n\n# test_sample.py::test_plain_fail\nknown bad\n"

        result = _run_pytest(tmp_path, test_src=test_src, md_src=md_src)
        output = result.stdout + result.stderr

        assert result.returncode == 0, output
        # 2 parametrizations matched by base id + 1 plain test = 3 xfailed; control passes.
        assert _count(output, "xfailed") == 3, output
        assert _count(output, "passed") == 1, output
        assert _count(output, "failed") == 0, output

    def test_parametrized_test_matched_by_base_id(self, tmp_path: Path) -> None:
        # The reported bug: a flaky parametrized test quarantined by its BASE id
        # (no ``[param]`` suffix) must be marked xfail for every parametrization.
        test_src = (
            "import pytest\n\n"
            '@pytest.mark.parametrize("case", ["a", "b", "c"])\n'
            "def test_flaky(case):\n"
            "    assert False\n"
        )
        md_src = "# test_sample.py::test_flaky\nflaky under load\n"

        result = _run_pytest(tmp_path, test_src=test_src, md_src=md_src)
        output = result.stdout + result.stderr

        assert result.returncode == 0, output
        assert _count(output, "xfailed") == 3, output
        assert _count(output, "failed") == 0, output

    def test_unlisted_failure_still_fails_the_suite(self, tmp_path: Path) -> None:
        # Control: proves the plugin is load-bearing — a failure that is NOT in
        # the list is reported normally and fails the run.
        test_src = "def test_not_listed():\n    assert False\n"
        md_src = "# test_sample.py::test_something_else\nunrelated\n"

        result = _run_pytest(tmp_path, test_src=test_src, md_src=md_src)
        output = result.stdout + result.stderr

        assert result.returncode != 0, output
        assert _count(output, "failed") == 1, output
        assert _count(output, "xfailed") == 0, output

    def test_report_header_lists_rules_at_start_of_run(self, tmp_path: Path) -> None:
        # The rules are printed in the run header (visible with normal/verbose
        # output; -v cancels the repo's default -q). Run with -v to assert it.
        test_src = "def test_plain_fail():\n    assert False\n"
        md_src = "# test_sample.py::test_plain_fail\nknown flaky under load\n"

        result = _run_pytest(tmp_path, test_src=test_src, md_src=md_src, extra_args=("-v",))
        output = result.stdout + result.stderr

        assert result.returncode == 0, output
        assert "url xfail: 1 rule(s)" in output, output
        assert "test_sample.py::test_plain_fail — known flaky under load" in output, output

    def test_listed_test_that_passes_is_tolerated(self, tmp_path: Path) -> None:
        # Non-strict xfail semantics: a listed test that unexpectedly passes is an
        # XPASS and does NOT fail the suite (the signal to remove it from the list).
        test_src = "def test_listed_but_passing():\n    assert True\n"
        md_src = "# test_sample.py::test_listed_but_passing\nexpected to fail\n"

        result = _run_pytest(tmp_path, test_src=test_src, md_src=md_src)
        output = result.stdout + result.stderr

        assert result.returncode == 0, output
        assert _count(output, "xpassed") == 1, output
        assert _count(output, "failed") == 0, output
