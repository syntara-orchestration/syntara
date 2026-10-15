"""CLI entry point for unified database seeding.

Usage::

    uv run python -m syntara.seed              # required seeders only
    uv run python -m syntara.seed --all        # include optional (dev) seeders
    uv run python -m syntara.seed --only settings credentials
    uv run python -m syntara.seed --only builtin_workflows --strict
    uv run python -m syntara.seed --list       # show registered seeders

Operational contract
--------------------
All seeders are **idempotent**: once the initial seed has populated the
database, the command may be executed again and must converge to the same
state without creating duplicates or failing on rows that already exist.

``--only builtin_workflows`` is expected to be re-run after the initial
seed, from a process that can reach Temporal, to create the Temporal
Schedules for built-in scheduled workflows. Two caveats on that re-run:
use the current release (an older build re-publishes old definitions as new
versions), and it includes its
``authz`` dependency, which re-asserts the seeded baseline — e.g. a
revoked role assignment is recreated. When Temporal is unreachable the
schedule sync logs a warning and the command still exits 0 by default;
pass ``--strict`` to abort on the first built-in seeding error and exit
non-zero, including validation, database, and schedule sync errors.
Already committed definitions remain durable; later definitions are left
for a subsequent run.
Changes to seeders must preserve these guarantees.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from syntara.audit.lifecycle import start_audit_subsystems, stop_audit_subsystems

logger = structlog.stdlib.get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m syntara.seed",
        description="Run database seeders after migrations.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Include optional (dev-only) seeders like sample workflows",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="NAME",
        help="Run only the named seeders (plus their dependencies)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "Abort on the first built-in workflow seeding error, including validation, "
            "database, and Temporal schedule sync errors (default: log and continue)"
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        default=False,
        dest="list_seeders",
        help="List registered seeders and exit",
    )
    return parser


async def _main(args: argparse.Namespace) -> None:
    failed = False
    try:
        start_audit_subsystems()
        from syntara.core.database.session import AsyncSessionLocal  # noqa: PLC0415
        from syntara.core.seed import get_seeders, run_seeders  # noqa: PLC0415

        if args.list_seeders:
            seeders = get_seeders(include_optional=True)
            for s in seeders:
                opt = " (optional)" if s.optional else ""
                deps = f" [depends: {', '.join(s.depends_on)}]" if s.depends_on else ""
                print(f"  {s.name}{opt}{deps} -- {s.description}")  # noqa: T201
            return

        await run_seeders(
            AsyncSessionLocal,
            include_optional=args.all,
            only=args.only,
            strict=args.strict,
        )
    except Exception:
        failed = True
        # Log while the stdout and OTLP handlers are still active, so shutdown
        # can flush this failure along with the other pending records.
        logger.exception("Seeding failed", strict=args.strict)
        raise
    finally:
        # --strict makes mid-run failure a normal outcome; the audit and log
        # buffers must still be flushed on that path.
        try:
            await stop_audit_subsystems()
        except Exception:
            logger.exception("Seeding shutdown failed", strict=args.strict)
            # Preserve an already logged startup/seeding error. A shutdown-only
            # failure still needs to propagate so the CLI exits non-zero.
            if not failed:
                raise


def main() -> None:
    """Parse arguments and run seeders."""
    parser = _build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(_main(args))
    except Exception:  # noqa: BLE001 — CLI boundary; _main logs before shutdown.
        sys.exit(1)


if __name__ == "__main__":
    main()
