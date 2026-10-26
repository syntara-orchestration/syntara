"""Typed Kafka source configuration; no Kafka client is required."""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from syntara.eventstreams.core.source_configuration import EventSourceConfiguration

# Upper bound for the system-generated consumer group identifier. Group IDs are
# built from the deployment, subscription and source generation, never supplied
# by a caller; the bound only guards against unexpected growth in persisted rows.
_MAX_GROUP_ID_LENGTH = 512


class KafkaSourceConfiguration(EventSourceConfiguration):
    """Fixed Kafka source address for one source generation; no secrets or payloads.

    ``topic`` and the generated ``group_id`` are immutable within a generation.
    ``cluster_id`` and ``topic_id`` are populated once during verified
    initialization where the broker exposes them; an identity change creates a
    new generation rather than mutating these fields.
    """

    transport: Literal["kafka"] = "kafka"
    topic: str = Field(min_length=1, max_length=249, pattern=r"^[a-zA-Z0-9._-]+$")
    group_id: str = Field(min_length=1, max_length=_MAX_GROUP_ID_LENGTH, repr=False)
    cluster_id: str | None = None
    topic_id: str | None = None
    # Tuple storage keeps the frozen configuration recursively immutable, while
    # JSON serialization retains the proposal's array/set representation.
    # None is legacy/uncaptured state, never inferred from current assignment.
    initial_partition_ids: tuple[Annotated[int, Field(strict=True, ge=0)], ...] | None = Field(
        default=None,
        min_length=1,
        description="System-managed first verified topic partition set; absent until captured",
    )

    @field_validator("initial_partition_ids")
    @classmethod
    def validate_initial_partition_ids(cls, value: tuple[int, ...] | None) -> tuple[int, ...] | None:
        """Require a unique set representation and serialize it in stable order."""
        if value is None:
            return None
        if len(set(value)) != len(value):
            msg = "initial_partition_ids must contain unique partition IDs"
            raise ValueError(msg)
        return tuple(sorted(value))

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        """Reject Kafka's reserved topic names, matching the Subscribe parameters."""
        if value in {".", ".."}:
            msg = "topic must be one exact Kafka topic"
            raise ValueError(msg)
        return value
