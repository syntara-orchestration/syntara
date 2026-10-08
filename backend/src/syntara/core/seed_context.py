"""Cross-module seeding state.

Holds the ``strict_mode`` ContextVar shared between the seeder runner
(:mod:`syntara.core.seed`) and individual seeders (e.g.
:mod:`syntara.workflows.seed_builtin`). It lives in its own leaf module so
domain seeders can read it without importing the runner — which would create
an import cycle, since the runner registers the seeders.
"""

from __future__ import annotations

from contextvars import ContextVar

# Set by run_seeders for the duration of a seed pass. Seeders that can degrade
# gracefully (e.g. a Temporal sync) read it to decide whether to raise instead.
strict_mode: ContextVar[bool] = ContextVar("seed_strict_mode", default=False)
