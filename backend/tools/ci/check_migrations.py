#!/usr/bin/env python3
"""Comprehensive Alembic migration validation using testcontainers.

Spins up a temporary PostgreSQL container (via Podman or Docker) and runs
four migration checks per database:
  1. Migration chain integrity (alembic history)
  2. No multiple heads (alembic heads)
  3. Pending changes detection (alembic upgrade head + alembic check)
  4. Full downgrade/upgrade round-trip
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
POSTGRES_IMAGE = os.getenv("POSTGRES_IMAGE", "quay.io/sclorg/postgresql-15-c9s")

RED = "\033[91m"
GREEN = "\033[92m"
BLUE = "\033[94m"
RESET = "\033[0m"


@dataclass(frozen=True)
class DatabaseConfig:
    """Alembic database configuration pointer."""

    name: str
    ini_file: str
    script_location: str


DATABASES: list[DatabaseConfig] = [
    DatabaseConfig(
        name="main",
        ini_file="alembic.ini",
        script_location="src/syntara/core/database/migrations",
    ),
]


def _get_alembic_config(db_config: DatabaseConfig, db_url: str) -> Config:
    alembic_cfg = Config(str(PROJECT_ROOT / db_config.ini_file))
    alembic_cfg.set_main_option(
        "script_location",
        str(PROJECT_ROOT / db_config.script_location),
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    return alembic_cfg


def check_migration_chain(cfg: Config, db_config: DatabaseConfig) -> bool:
    """Walk the full revision history; return False if the chain is broken."""
    print(f"\n{BLUE}📋 [{db_config.name}] Step 1: Validating migration chain...{RESET}")
    try:
        script = ScriptDirectory.from_config(cfg)
        list(script.walk_revisions())
    except Exception as exc:
        print(f"{RED}❌ [{db_config.name}] Migration chain is broken!{RESET}", file=sys.stderr)
        print(f"   {exc}", file=sys.stderr)
        print("\nThis usually means:", file=sys.stderr)
        print("  - A migration file was deleted", file=sys.stderr)
        print("  - A migration references a missing parent", file=sys.stderr)
        print("  - Merge conflicts weren't properly resolved", file=sys.stderr)
        return False
    print(f"{GREEN}✅ [{db_config.name}] Migration chain is valid{RESET}")
    return True


def check_multiple_heads(cfg: Config, db_config: DatabaseConfig) -> bool:
    """Detect multiple migration heads; return False if found."""
    print(f"\n{BLUE}📋 [{db_config.name}] Step 2: Checking for multiple heads...{RESET}")
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) > 1:
        print(
            f"{RED}❌ [{db_config.name}] Multiple migration heads detected ({len(heads)} heads)!{RESET}",
            file=sys.stderr,
        )
        print("\nMigration heads:", file=sys.stderr)
        for head in heads:
            print(f"  {head}", file=sys.stderr)
        print(
            f"\nMerge them with: alembic -c {db_config.ini_file} merge -m 'merge heads' <rev1> <rev2>",
            file=sys.stderr,
        )
        return False
    print(f"{GREEN}✅ [{db_config.name}] No multiple heads detected{RESET}")
    return True


def check_pending_migrations(cfg: Config, db_config: DatabaseConfig) -> bool:
    """Apply migrations to head and verify no un-generated changes exist in models."""
    print(f"\n{BLUE}📋 [{db_config.name}] Step 3: Applying migrations and checking for pending changes...{RESET}")
    print("   Upgrading to head...")
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:
        print(f"{RED}❌ [{db_config.name}] Failed to upgrade to head{RESET}", file=sys.stderr)
        print(f"   {exc}", file=sys.stderr)
        return False

    print("   Checking for pending migrations...")
    try:
        command.check(cfg)
    except CommandError as exc:
        msg = f"{RED}❌ [{db_config.name}] Pending migrations detected or models don't match migrations!{RESET}"
        print(msg, file=sys.stderr)
        print(f"   {exc}", file=sys.stderr)
        print("\nThis usually means:", file=sys.stderr)
        print("  - Models were changed without creating a migration", file=sys.stderr)
        print(
            f"  - Run 'alembic -c {db_config.ini_file} revision --autogenerate -m \"description\"'",
            file=sys.stderr,
        )
        return False
    print(f"{GREEN}✅ [{db_config.name}] No pending migrations, models match migrations{RESET}")
    return True


def check_downgrade_upgrade(cfg: Config, db_config: DatabaseConfig) -> bool:
    """Downgrade to base then upgrade to head; return False on failure."""
    print(f"\n{BLUE}📋 [{db_config.name}] Step 4: Testing downgrade/upgrade consistency...{RESET}")
    print("   Downgrading to base (removing all migrations)...")
    try:
        command.downgrade(cfg, "base")
    except Exception as exc:
        print(f"{RED}❌ [{db_config.name}] Downgrade to base failed!{RESET}", file=sys.stderr)
        print(f"   {exc}", file=sys.stderr)
        print("\nThis usually means:", file=sys.stderr)
        print("  - A downgrade() function in one of the migrations is broken", file=sys.stderr)
        print("  - Missing or incorrect downgrade logic", file=sys.stderr)
        return False

    print("   Upgrading back to head...")
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:
        print(f"{RED}❌ [{db_config.name}] Upgrade to head failed after downgrade!{RESET}", file=sys.stderr)
        print(f"   {exc}", file=sys.stderr)
        return False

    print(f"{GREEN}✅ [{db_config.name}] Full downgrade/upgrade cycle successful{RESET}")
    return True


def main() -> None:
    """Run all migration checks, spinning up a testcontainer for DB-backed steps."""
    print(f"{BLUE}🔍 Running comprehensive migration checks for {len(DATABASES)} database(s)...{RESET}")

    failures: list[str] = []

    # Steps 1-2 only read migration files from disk — no DB needed.
    # Run them first so we fail fast before spinning up a container.
    for db_config in DATABASES:
        print(f"\n{BLUE}{'=' * 60}{RESET}")
        print(f"{BLUE}  Checking database: {db_config.name} ({db_config.ini_file}){RESET}")
        print(f"{BLUE}{'=' * 60}{RESET}")

        cfg_no_db = _get_alembic_config(db_config, "sqlite://")
        if not check_migration_chain(cfg_no_db, db_config):
            failures.append(f"{db_config.name}: migration chain")
        if not check_multiple_heads(cfg_no_db, db_config):
            failures.append(f"{db_config.name}: multiple heads")

    print(f"\n   Using image: {POSTGRES_IMAGE}")
    pg_container = PostgresContainer(POSTGRES_IMAGE)
    # sclorg images require POSTGRESQL_* env vars instead of POSTGRES_*
    if "sclorg" in POSTGRES_IMAGE:
        pg_container.with_env("POSTGRESQL_USER", pg_container.username)
        pg_container.with_env("POSTGRESQL_PASSWORD", pg_container.password)
        pg_container.with_env("POSTGRESQL_DATABASE", pg_container.dbname)
    with pg_container as pg:
        db_url = pg.get_connection_url(driver="asyncpg")

        for db_config in DATABASES:
            print(f"\n{BLUE}{'=' * 60}{RESET}")
            print(f"{BLUE}  DB checks: {db_config.name} ({db_config.ini_file}){RESET}")
            print(f"{BLUE}{'=' * 60}{RESET}")

            cfg = _get_alembic_config(db_config, db_url)
            if not check_pending_migrations(cfg, db_config):
                failures.append(f"{db_config.name}: pending migrations")
            if not check_downgrade_upgrade(cfg, db_config):
                failures.append(f"{db_config.name}: downgrade/upgrade")

    if failures:
        print(f"\n{RED}❌ Migration checks failed:{RESET}", file=sys.stderr)
        for failure in failures:
            print(f"   - {failure}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{GREEN}✅ All migration checks passed for all databases!{RESET}")


if __name__ == "__main__":
    main()
