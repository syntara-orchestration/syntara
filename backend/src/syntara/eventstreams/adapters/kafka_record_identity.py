"""Kafka record coordinates without a Kafka client dependency."""

from typing import Literal

from pydantic import Field, field_serializer, field_validator

from syntara.eventstreams.core.record_identity import EventRecordIdentity


class KafkaRecordIdentity(EventRecordIdentity):
    """A single topic/partition/offset within an immutable source generation."""

    transport: Literal["kafka"] = "kafka"
    topic: str = Field(min_length=1, max_length=249, pattern=r"^[a-zA-Z0-9._-]+$")
    partition: int = Field(ge=0, le=2**31 - 1, strict=True)
    offset: int = Field(ge=0, le=2**63 - 1, strict=True)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        """Use the same exact-topic restriction as the source configuration."""
        if value in {".", ".."}:
            msg = "topic must be one exact Kafka topic"
            raise ValueError(msg)
        return value

    @field_validator("offset", mode="before")
    @classmethod
    def parse_offset(cls, value: object) -> object:
        """Accept the lossless decimal-string JSON representation."""
        if (
            isinstance(value, str)
            and value.isascii()
            and value.isdecimal()
            and (value == "0" or not value.startswith("0"))
        ):
            return int(value)
        return value

    @field_serializer("offset", when_used="json")
    def serialize_offset(self, value: int) -> str:
        """Keep Kafka's BIGINT offset lossless for JSON consumers."""
        return str(value)
