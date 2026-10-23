"""Approval module's engine-independent activity registrations."""

from syntara.approvals.activities import ApprovalActivities
from syntara.workflow_runtime.providers import ActivityProvider, ActivityProviderContext
from syntara.workflow_runtime.registry import ActivityDefinition, ActivityRegistry


def _register_approval_activities(registry: ActivityRegistry, activities: ApprovalActivities) -> None:
    """Install approval handlers; worker composition selects queues and dependencies."""
    registry.register(
        ActivityDefinition(
            "approval.request",
            1,
            activities.request,
            supports_deferred=True,
            cancel_handler=activities.cancel,
            expire_handler=activities.expire,
        )
    )


class ApprovalActivityProvider:
    """Construct and register approval activities from worker dependencies."""

    def __init__(self, context: ActivityProviderContext) -> None:
        """Create the provider using only shared worker infrastructure."""
        self.activities = ApprovalActivities(context.session_factory)

    def register(self, registry: ActivityRegistry) -> None:
        """Register approval activity definitions."""
        _register_approval_activities(registry, self.activities)


def create_activity_provider(context: ActivityProviderContext) -> ActivityProvider:
    """Create the approval domain provider for worker startup discovery."""
    return ApprovalActivityProvider(context)


def register_approval_activities(registry: ActivityRegistry, activities: ApprovalActivities) -> None:
    """Register explicit handlers for tests and embedded worker integrations."""
    _register_approval_activities(registry, activities)
