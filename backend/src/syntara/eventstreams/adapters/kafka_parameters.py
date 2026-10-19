"""Kafka Subscribe definition schema without broker client dependencies."""

from pydantic import Field, field_validator

from syntara.eventstreams.core.subscribe_parameters import EventSubscribeParameters


class KafkaSubscribeParameters(EventSubscribeParameters):
    """One exact topic; consumer groups and connection settings are not inputs.

    Tightens the transport-neutral ``topic`` with Kafka's naming constraints.
    """

    topic: str = Field(min_length=1, max_length=249, pattern=r"^[a-zA-Z0-9._-]+$")

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        """Reject Kafka's reserved topic names."""
        if value in {".", ".."}:
            msg = "topic must be one exact Kafka topic"
            raise ValueError(msg)
        return value
