"""Kafka Subscribe definition schema without broker client dependencies."""

from pydantic import Field, field_validator

from syntara.eventstreams.adapters.kafka_start_configuration import KafkaStartConfiguration
from syntara.eventstreams.core.draft_parameters import EventSubscribeDraftParameters
from syntara.eventstreams.core.subscribe_parameters import EventSubscribeParameters


class KafkaSubscribeParameters(EventSubscribeParameters):
    """One exact topic and approved reading controls; no connection overrides."""

    topic: str = Field(min_length=1, max_length=249, pattern=r"^[a-zA-Z0-9._-]+$")
    start: KafkaStartConfiguration = Field(default_factory=KafkaStartConfiguration)
    group_id: str | None = Field(default=None, min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9._-]+$")

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        """Reject Kafka's reserved topic names."""
        if value in {".", ".."}:
            msg = "topic must be one exact Kafka topic"
            raise ValueError(msg)
        return value


class KafkaSubscribeDraftParameters(EventSubscribeDraftParameters):
    """Validate supplied Kafka fields while required draft bindings are missing."""

    topic: str | None = Field(default=None, min_length=1, max_length=249, pattern=r"^[a-zA-Z0-9._-]+$")
    start: KafkaStartConfiguration = Field(default_factory=KafkaStartConfiguration)
    group_id: str | None = Field(default=None, min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9._-]+$")

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str | None) -> str | None:
        """Reject reserved names even in drafts."""
        if value in {".", ".."}:
            msg = "topic must be one exact Kafka topic"
            raise ValueError(msg)
        return value
