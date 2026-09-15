"""RSS leak canary for regopy evaluations inside the full application process.

Guards the import-order fix in ``syntara/__init__.py``: with regopy loaded
first, 800 evaluations grow RSS by well under 1 MB; if another native library
claims the libstdc++ allocator bindings first, the same loop leaks ~55 MB
(~69 KB per evaluation).  The threshold sits between the two regimes so a
regression fails loudly without flaking on allocator noise.

Runs in a subprocess so the measured process imports the app the same way a
real API worker does.
"""

import os
import re
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("regopy")

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="reads VmRSS from /proc, Linux only")


@pytest.fixture(autouse=True)
def _skip_if_no_opa() -> None:
    """Override the directory-wide opa-CLI guard: the canary only needs regopy."""


_WARMUP_EVALS = 100
_MEASURED_EVALS = 800
# Healthy runs measure 0.06-0.2 KB per evaluation; the allocator-mismatch
# regression is ~69 KB. A per-eval bound of 5 KB keeps ~25x headroom over
# measured noise while failing on anything above ~7% of the original leak
# (the previous 25 MB total bound would have passed a 32 KB/eval regression).
_MAX_GROWTH_KB_PER_EVAL = 5.0

_CANARY_CODE = f"""
import gc

import syntara.api.main  # noqa: F401  # full app import, mirrors a real API process

from syntara.authz import _rego_runtime
from syntara.authz.evaluator import get_default_policy_path


def rss_kb() -> int:
    with open("/proc/self/status") as status:
        for line in status:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return 0


policy = get_default_policy_path()
_rego_runtime.init(policy.name, policy.read_text(encoding="utf-8"))

authz_input = {{
    "user": {{"id": "canary", "labels": {{}}, "metadata": {{}}}},
    "action": "read",
    "resource": {{"type": "workflow", "id": "canary", "project": "", "labels": {{}}, "metadata": {{}}}},
    "groups": [],
    "effective_policies": [],
}}

for _ in range({_WARMUP_EVALS}):
    _rego_runtime.evaluate(authz_input)
gc.collect()
before = rss_kb()

for _ in range({_MEASURED_EVALS}):
    _rego_runtime.evaluate(authz_input)
gc.collect()
after = rss_kb()

print(f"GROWTH_KB={{after - before}}")
"""


def test_rego_eval_rss_growth_stays_bounded():
    """800 in-app evaluations must not leak MB-scale native memory."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", textwrap.dedent(_CANARY_CODE)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    match = re.search(r"GROWTH_KB=(-?\d+)", result.stdout)
    assert match, f"canary did not report growth: stdout={result.stdout}"
    growth_kb = int(match.group(1))
    growth_kb_per_eval = growth_kb / _MEASURED_EVALS

    assert growth_kb_per_eval < _MAX_GROWTH_KB_PER_EVAL, (
        f"RSS grew {growth_kb / 1024:.1f} MB over {_MEASURED_EVALS} evaluations "
        f"({growth_kb_per_eval:.1f} KB/eval, limit {_MAX_GROWTH_KB_PER_EVAL}) — a native "
        "leak per rego evaluation is back. Check that regopy is imported before "
        "greenlet/temporalio (syntara/__init__.py preload; "
        "docs/standards/imports-and-modules.md)."
    )
