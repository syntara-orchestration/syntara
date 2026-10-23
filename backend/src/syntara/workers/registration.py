"""Discover domain activity providers at worker startup."""

from syntara.core.database.session import AsyncSessionLocal
from syntara.workflow_runtime.providers import ActivityProviderContext, discover_activity_providers
from syntara.workflow_runtime.registry import ActivityRegistry


def build_activity_registry() -> ActivityRegistry:
    """Discover and install domain-owned activities used by the V2 worker."""
    registry = ActivityRegistry()
    context = ActivityProviderContext(session_factory=AsyncSessionLocal)
    for factory in discover_activity_providers():
        factory(context).register(registry)
    return registry
