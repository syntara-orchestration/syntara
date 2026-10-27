"""Discovery and composition contracts for domain-owned activities."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Protocol, cast

import syntara

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.workflow_runtime.registry import ActivityRegistry

ENTRY_POINT_GROUP = "syntara.workflow_activities"


@dataclass(frozen=True)
class ActivityProviderContext:
    """Shared worker infrastructure supplied to domain activity providers."""

    session_factory: async_sessionmaker[AsyncSession]


class ActivityProvider(Protocol):
    """Domain-owned activity registration object."""

    def register(self, registry: ActivityRegistry) -> None:
        """Register this provider's definitions."""


ActivityProviderFactory = Callable[[ActivityProviderContext], ActivityProvider]


def _entry_point_factories() -> Iterator[ActivityProviderFactory]:
    """Yield providers exported by installed domain packages."""
    selected = entry_points(group=ENTRY_POINT_GROUP)
    for entry_point in selected:
        loaded = entry_point.load()
        yield cast("ActivityProviderFactory", loaded)


def _builtin_factories() -> Iterator[ActivityProviderFactory]:
    """Discover activity-provider modules in the monorepo's domain packages."""
    for package in pkgutil.iter_modules(syntara.__path__, f"{syntara.__name__}."):
        provider_module = f"{package.name}.activity_provider"
        if importlib.util.find_spec(provider_module) is None:
            continue
        module = importlib.import_module(provider_module)
        factory = getattr(module, "create_activity_provider", None)
        if factory is not None:
            yield cast("ActivityProviderFactory", factory)


def discover_activity_providers() -> tuple[ActivityProviderFactory, ...]:
    """Discover installed plugin providers and built-in domain providers."""
    factories: list[ActivityProviderFactory] = []
    seen: set[tuple[str, str]] = set()
    for factory in (*_entry_point_factories(), *_builtin_factories()):
        identity = (factory.__module__, getattr(factory, "__qualname__", repr(factory)))
        if identity not in seen:
            seen.add(identity)
            factories.append(factory)
    return tuple(factories)
