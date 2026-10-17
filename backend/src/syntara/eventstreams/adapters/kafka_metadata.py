"""Typed Kafka source coordinates; no Kafka client is required."""

from enum import StrEnum

from pydantic import Field

from syntara.eventstreams.core.envelope import EventSourceMetadata


class KafkaTimestampType(StrEnum):
    """Timestamp meanings supplied by Kafka."""

    create_time = "create_time"
    log_append_time = "log_append_time"


class KafkaSourceMetadata(EventSourceMetadata):
    """Adapter-supplied metadata with lossless decimal-string offsets."""

    topic: str = Field(min_length=1, repr=False)
    partition: int = Field(ge=0, strict=True)
    offset: str = Field(pattern=r"^(0|[1-9][0-9]*)$", strict=True)
    timestamp_ms: int | None = Field(default=None, strict=True)
    timestamp_type: KafkaTimestampType | None = None
