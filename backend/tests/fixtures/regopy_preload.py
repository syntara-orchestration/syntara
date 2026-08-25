"""Session guard: the pytest process itself must load regopy before greenlet.

The subprocess order tests and the RSS leak canary validate clean child
processes; this guard covers the pytest process, whose in-process rego
evaluations (compatibility corpus, RBAC/ABAC suites — thousands per run)
would each leak ~69 KB of native memory if a plugin or conftest imported
greenlet before ``tests/conftest.py`` preloaded regopy.  See
``docs/standards/imports-and-modules.md`` ("Native import order: regopy
loads first").

Known exception: coverage jobs. ``[tool.coverage.run] concurrency`` includes
``greenlet``, so under ``--cov`` the tracer imports greenlet before any
conftest can run — unavoidable while coverage traces greenlet contexts.  In
that case the pytest process accepts the per-eval leak for the duration of
the job and the guard downgrades to a warning; the leak canary (a clean
subprocess) still gates the production import order.
"""

import sys
import warnings

import pytest

# Keep in sync with syntara.authz.evaluator._NATIVE_ALLOCATOR_CLAIMANTS.
# Not imported from there: that module needs a loadable regopy, and this guard
# must also work in collection-only environments where regopy cannot load.
_NATIVE_ALLOCATOR_CLAIMANTS = ("greenlet", "temporalio.bridge.temporal_sdk_bridge")


@pytest.fixture(scope="session", autouse=True)
def _regopy_preload_order_guard() -> None:
    """Fail the session when the in-process regopy-first guarantee is lost."""
    if "regopy" not in sys.modules:
        # regopy unavailable (collection-only environments) — nothing to guard.
        return
    modules = list(sys.modules)
    regopy_index = modules.index("regopy")
    offenders = [
        name for name in _NATIVE_ALLOCATOR_CLAIMANTS if name in sys.modules and modules.index(name) < regopy_index
    ]
    if "greenlet" in offenders and "coverage" in modules and modules.index("coverage") < modules.index("greenlet"):
        # Coverage-owned import (concurrency = ["greenlet"]): accepted for this
        # process, but keep it visible in the warnings summary.
        offenders.remove("greenlet")
        warnings.warn(
            "coverage imported greenlet before regopy (concurrency tracing): "
            "in-process rego evaluations leak ~69 KB each for this coverage job. "
            "The subprocess leak canary still gates the production import order.",
            stacklevel=2,
        )
    if offenders:
        pytest.fail(
            f"{offenders} imported before regopy in the pytest process — every "
            "in-process rego evaluation this session leaks ~69 KB of native "
            "memory. The preload in tests/conftest.py must run before anything "
            "imports greenlet or temporalio's bridge (see "
            "docs/standards/imports-and-modules.md, 'Native import order')."
        )
