"""Subprocess integration tests for ``@pytest.mark.xfail_openrouter_credits``.

Runs a real pytest session with only this plugin loaded. ``APP_OPENROUTER_API_KEY``
is unset in the child so setup does not call OpenRouter; these tests cover the
failure-text conversion path.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# tests/unit/fixtures/test_xfail_openrouter_credits_integration.py -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _run_pytest(tmp_path: Path, *, test_src: str) -> subprocess.CompletedProcess[str]:
    """Run pytest over *test_src* in an isolated subprocess with this plugin."""
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts =\nmarkers =\n    xfail_openrouter_credits: credit-gated xfail\n"
    )
    (tmp_path / "test_sample.py").write_text(test_src)

    env = {
        **os.environ,
        "PYTHONPATH": str(_BACKEND_ROOT),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    env.pop("APP_OPENROUTER_API_KEY", None)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(tmp_path),
        "-p",
        "tests.fixtures.xfail_openrouter_credits",
        "-p",
        "no:cacheprovider",
        "-q",
    ]
    return subprocess.run(cmd, cwd=tmp_path, env=env, capture_output=True, text=True, check=False)  # noqa: S603


def _count(output: str, word: str) -> int:
    """Extract the ``<n> <word>`` count from pytest's summary line (0 if absent)."""
    match = re.search(rf"(\d+) {word}", output)
    return int(match.group(1)) if match else 0


class TestXfailOpenrouterCreditsIntegration:
    """Run the plugin in a real (sub)pytest session and assert on the outcome."""

    def test_credit_failure_is_xfailed(self, tmp_path: Path) -> None:
        test_src = (
            "import pytest\n\n"
            "@pytest.mark.xfail_openrouter_credits\n"
            "def test_credits():\n"
            '    raise AssertionError("Failed: INSUFFICIENT_CREDITS")\n'
        )
        result = _run_pytest(tmp_path, test_src=test_src)
        output = result.stdout + result.stderr

        assert result.returncode == 0, output
        assert _count(output, "xfailed") == 1, output
        assert _count(output, "failed") == 0, output

    def test_unrelated_failure_still_fails_the_suite(self, tmp_path: Path) -> None:
        test_src = (
            "import pytest\n\n"
            "@pytest.mark.xfail_openrouter_credits\n"
            "def test_script_bug():\n"
            '    raise AssertionError("Failed: agent: An unexpected error occurred during LLM streaming")\n'
        )
        result = _run_pytest(tmp_path, test_src=test_src)
        output = result.stdout + result.stderr

        assert result.returncode != 0, output
        assert _count(output, "failed") == 1, output
        assert _count(output, "xfailed") == 0, output

    def test_unmarked_credit_failure_still_fails(self, tmp_path: Path) -> None:
        test_src = 'def test_unmarked():\n    raise AssertionError("INSUFFICIENT_CREDITS")\n'
        result = _run_pytest(tmp_path, test_src=test_src)
        output = result.stdout + result.stderr

        assert result.returncode != 0, output
        assert _count(output, "failed") == 1, output
        assert _count(output, "xfailed") == 0, output

    def test_passing_marked_test_is_a_pass_not_xpass(self, tmp_path: Path) -> None:
        test_src = "import pytest\n\n@pytest.mark.xfail_openrouter_credits\ndef test_ok():\n    assert True\n"
        result = _run_pytest(tmp_path, test_src=test_src)
        output = result.stdout + result.stderr

        assert result.returncode == 0, output
        assert _count(output, "passed") == 1, output
        assert _count(output, "xpassed") == 0, output
        assert _count(output, "xfailed") == 0, output
