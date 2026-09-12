"""CLI entry point for unified database seeding.

Usage::

    uv run python -m syntara.seed              # required seeders only
    uv run python -m syntara.seed --all        # include optional (dev) seeders
    uv run python -m syntara.seed --only settings credentials
    uv run python -m syntara.seed --list       # show registered seeders

Operational contract
--------------------
Seeders must be **idempotent** and re-runs must be **safe to run
concurrently**: once the initial seed has populated the database, the command
may be executed again at any time and from several processes at once
(deployment hooks, pod init containers, replicas starting together) and must
converge to the same state without creating duplicates or failing on rows
that already exist. In particular ``--only builtin_workflows`` is expected to
be re-run after the initial seed, from a process that can reach Temporal, to
create the Temporal Schedules for built-in scheduled workflows; when Temporal
is unreachable that step logs a warning and the command still exits 0.
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
        "--list",
        action="store_true",
        default=False,
        dest="list_seeders",
        help="List registered seeders and exit",
    )
    return parser


async def _main(args: argparse.Namespace) -> None:
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
    )

    await stop_audit_subsystems()


def main() -> None:
    """Parse arguments and run seeders."""
    parser = _build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(_main(args))
    except Exception:
        logger.exception("Seeding failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
