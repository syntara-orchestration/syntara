"""Domain exceptions for event stream subscriptions."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


@fastapi_exception(handler="syntara.eventstreams.error_handlers.event_stream_error_handler")
class EventStreamError(SyntaraError):
    """Base exception for all event stream subscription errors."""


@fastapi_exception(handler="syntara.eventstreams.error_handlers.event_subscription_in_use_error_handler")
class EventSubscriptionInUseError(EventStreamError):
    """Raised when deleting a resource still bound by event-subscription evidence.

    Deletion is blocked conservatively while a non-retired subscription or source
    still references the workflow, Integration or credential. Retirement alone
    does not authorize deletion; recovery-aware evidence release is coordinated by
    a later story, so the caller must resolve the bound subscriptions first.
    """

    def __init__(self, resource_kind: str, resource_name: str, total_count: int) -> None:
        """Initialize with the referenced resource and the number of bound subscriptions.

        Args:
            resource_kind: The kind of resource being deleted (workflow, integration, credential).
            resource_name: The human-readable name of that resource.
            total_count: Number of bound event subscriptions blocking deletion.

        """
        self.resource_kind = resource_kind
        self.resource_name = resource_name
        self.total_count = total_count

        plural = "s" if total_count != 1 else ""
        super().__init__(
            f"Cannot delete {resource_kind} '{resource_name}': still bound by "
            f"{total_count} event subscription{plural} (including retired ones). "
            "Bound subscription evidence blocks deletion until it is released by a "
            "recovery-aware operation; retirement alone does not unblock it."
        )
