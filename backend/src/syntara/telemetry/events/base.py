"""Base telemetry event class.

Provides the abstract base for all telemetry events transmitted to Segment.com.
"""

import re
from functools import lru_cache
from uuid import UUID

from sqlmodel import Field, SQLModel


@lru_cache
def _get_container_image_version() -> str:
    """Return the container image version (cached for process lifetime).

    Returns:
        The container image version string from application settings.

    """
    from syntara.core.config.base import get_settings  # noqa: PLC0415

    return get_settings().container_image_version


class BaseTelemetryEvent(SQLModel):
    """Abstract base class for all telemetry events.

    All telemetry events inherit from this base. The to_segment_event() method
    provides a default implementation that converts the event to Segment Track API format.

    The event name is derived from the class name by converting CamelCase to
    snake_case and removing the "Event" suffix.

    ``container_image_version`` is included in every event's ``properties`` so
    that it propagates to Amplitude (Segment's Amplitude destination maps event
    properties but drops the context dict), enabling CI/devel builds to be
    filtered out from customer data.

    """

    model_config = {"frozen": True}
    entitlement_id: str = Field(..., description="Installation identifier")
    request_id: UUID | None = Field(
        default=None,
        description="Optional X-Request-Id (UUID) from the originating HTTP request",
    )

    @classmethod
    def _get_event_name(cls) -> str:
        """Get the Segment event name for this event class.

        Derives the name from the class name by converting CamelCase to
        snake_case and removing the "Event" suffix.

        Returns:
            The event name string in snake_case format.

        """
        name = cls.__name__.removesuffix("Event")
        name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
        return name.lower()

    def to_segment_event(self) -> dict[str, object]:
        """Convert to Segment Track API format.

        ``container_image_version`` is added to ``properties`` (rather than the
        Segment context dict) so that it reaches Amplitude for build filtering.

        Returns:
            Dictionary with event name and properties for Segment Track API.

        """
        properties = self.model_dump()
        properties["container_image_version"] = _get_container_image_version()
        return {
            "event": self._get_event_name(),
            "properties": properties,
        }
