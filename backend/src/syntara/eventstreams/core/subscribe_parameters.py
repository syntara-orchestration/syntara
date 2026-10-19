"""Transport-neutral, literal bindings for event Subscribe definitions."""

from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel


class EventSubscribeParameters(SQLModel):
    """Resource references fixed before an event execution exists.

    The transport (Kafka, MQTT, …) is a property of the referenced Integration,
    resolved server-side from ``integration_id`` — it is intentionally NOT a
    client-supplied field. Transport-specific field rules (e.g. Kafka topic
    naming) are enforced by the concrete subclass selected from the Integration
    type; see ``adapters.subscribe_parameters.validate_event_subscribe_parameters``.
    """

    integration_id: UUID
    credential_id: UUID
    topic: str = Field(min_length=1, max_length=1024)
    input_schema: dict[str, Any] | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
