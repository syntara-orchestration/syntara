"""Unified seeder registry for post-migration data seeding.

Provides a single entry point for all database seeding operations,
replacing the scattered compose command chain and lifespan seeding.

Each domain registers a seeder function with metadata (name, dependencies,
optional flag).  ``run_seeders`` executes them in dependency-safe order,
opening a fresh session per seeder.

Usage (CLI)::

    uv run python -m syntara.seed              # required seeders only
    uv run python -m syntara.seed --all        # include optional (dev) seeders
    uv run python -m syntara.seed --only settings credentials
    uv run python -m syntara.seed --list       # show registered seeders
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from sqlmodel.ext.asyncio.session import AsyncSession

    SeederFunc = Callable[[AsyncSession], Coroutine[Any, Any, None]]

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SeederRegistration:
    """A registered seeder with metadata for ordering and filtering."""

    name: str
    func: SeederFunc
    depends_on: tuple[str, ...] = ()
    optional: bool = False
    description: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_SEEDERS: list[SeederRegistration] = []


def _register(reg: SeederRegistration) -> None:
    """Add a seeder to the registry. Raises on duplicate names."""
    if any(s.name == reg.name for s in _SEEDERS):
        msg = f"Duplicate seeder name: {reg.name!r}"
        raise ValueError(msg)
    _SEEDERS.append(reg)


def get_seeders(*, include_optional: bool = False) -> list[SeederRegistration]:
    """Return seeders in dependency-safe execution order."""
    pool = [s for s in _SEEDERS if include_optional or not s.optional]
    return _topological_sort(pool)


def get_seeder(name: str) -> SeederRegistration:
    """Look up a single seeder by name. Raises ``KeyError`` if not found."""
    for s in _SEEDERS:
        if s.name == name:
            return s
    msg = f"Unknown seeder: {name!r}. Available: {[s.name for s in _SEEDERS]}"
    raise KeyError(msg)


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


def _topological_sort(seeders: list[SeederRegistration]) -> list[SeederRegistration]:
    """Kahn's algorithm over ``depends_on`` edges.

    Dependencies not in *seeders* (filtered out or already satisfied) are
    silently skipped.  Truly unknown dependencies raise ``ValueError``.
    """
    by_name = {s.name: s for s in seeders}
    in_degree: dict[str, int] = {s.name: 0 for s in seeders}
    dependents: dict[str, list[str]] = {s.name: [] for s in seeders}

    for s in seeders:
        for dep in s.depends_on:
            if dep not in by_name:
                # Filtered out of current pool — only error if truly unknown.
                if not any(r.name == dep for r in _SEEDERS):
                    msg = f"Seeder {s.name!r} depends on unknown seeder {dep!r}"
                    raise ValueError(msg)
                continue
            in_degree[s.name] += 1
            dependents[dep].append(s.name)

    queue = sorted(name for name, deg in in_degree.items() if deg == 0)
    result: list[SeederRegistration] = []

    while queue:
        name = queue.pop(0)
        result.append(by_name[name])
        for dependent in dependents[name]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
                queue.sort()

    if len(result) != len(seeders):
        remaining = set(by_name) - {s.name for s in result}
        msg = f"Dependency cycle detected among seeders: {remaining}"
        raise ValueError(msg)

    return result


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_seeders(
    session_factory: Any,  # noqa: ANN401
    *,
    include_optional: bool = False,
    only: list[str] | None = None,
) -> None:
    """Execute seeders in dependency order.

    Opens a fresh session per seeder so each commits independently.

    Args:
        session_factory: ``async_sessionmaker`` or compatible callable.
        include_optional: Include optional (dev-only) seeders.
        only: If provided, run only these named seeders (plus dependencies).

    """
    if only:
        to_run = _resolve_with_deps(set(only))
        ordered = _topological_sort(to_run)
    else:
        ordered = get_seeders(include_optional=include_optional)

    logger.info("seed.run.start", seeders=[s.name for s in ordered])

    for seeder in ordered:
        logger.info("seed.run.seeder", name=seeder.name)
        async with session_factory() as session:
            await seeder.func(session)
        logger.info("seed.run.seeder.done", name=seeder.name)

    logger.info("seed.run.complete", count=len(ordered))


def _resolve_with_deps(names: set[str]) -> list[SeederRegistration]:
    """Resolve a set of seeder names to include transitive dependencies."""
    resolved: dict[str, SeederRegistration] = {}
    stack = list(names)

    while stack:
        name = stack.pop()
        if name in resolved:
            continue
        seeder = get_seeder(name)
        resolved[name] = seeder
        stack.extend(dep for dep in seeder.depends_on if dep not in resolved)

    return list(resolved.values())


# ---------------------------------------------------------------------------
# Registration (lazy imports to avoid circular dependencies)
# ---------------------------------------------------------------------------


def _register_all() -> None:
    """Register all known seeders."""
    from syntara.audit.seed import seed_audit_metadata  # noqa: PLC0415
    from syntara.authz.seed import seed_groups_project_admin  # noqa: PLC0415
    from syntara.credentials.lib.preseed import preseed_credential_types  # noqa: PLC0415
    from syntara.settings.seeder import seed_settings_with_session  # noqa: PLC0415
    from syntara.workflows.seed_builtin import seed_builtin_workflows  # noqa: PLC0415

    _register(
        SeederRegistration(
            name="settings",
            func=seed_settings_with_session,
            description="Upsert setting categories and runtime settings catalog",
        )
    )
    _register(
        SeederRegistration(
            name="credentials",
            func=preseed_credential_types,
            description="Create/update managed credential types",
        )
    )
    _register(
        SeederRegistration(
            name="authz",
            func=seed_groups_project_admin,
            description="Seed built-in groups, default project, and admin user",
        )
    )
    _register(
        SeederRegistration(
            name="audit_metadata",
            func=seed_audit_metadata,
            description="Populate audit_table_metadata and create audit triggers",
        )
    )
    _register(
        SeederRegistration(
            name="builtin_workflows",
            func=seed_builtin_workflows,
            depends_on=("authz",),
            description="Seed built-in workflows (document conversion, invocation execution)",
        )
    )


_register_all()
