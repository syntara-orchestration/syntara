"""Invocation domain activity registrations."""

from syntara.invocations.activities import InvocationActivities
from syntara.workflow_runtime.providers import ActivityProvider, ActivityProviderContext
from syntara.workflow_runtime.registry import ActivityDefinition, ActivityRegistry


def _register_invocation_activities(registry: ActivityRegistry, activities: InvocationActivities) -> None:
    """Install the invocation-owned synchronous agent activity."""
    registry.register(ActivityDefinition("invocation.execute", 1, activities.execute, cancel_handler=activities.cancel))


class InvocationActivityProvider:
    """Construct and register invocation activities from worker dependencies."""

    def __init__(self, context: ActivityProviderContext) -> None:
        """Create the provider using only shared worker infrastructure."""
        self.activities = InvocationActivities(context.session_factory)

    def register(self, registry: ActivityRegistry) -> None:
        """Register invocation activity definitions."""
        _register_invocation_activities(registry, self.activities)


def create_activity_provider(context: ActivityProviderContext) -> ActivityProvider:
    """Create the invocation domain provider for worker startup discovery."""
    return InvocationActivityProvider(context)


def register_invocation_activities(registry: ActivityRegistry, activities: InvocationActivities) -> None:
    """Register explicit handlers for tests and embedded worker integrations."""
    _register_invocation_activities(registry, activities)
