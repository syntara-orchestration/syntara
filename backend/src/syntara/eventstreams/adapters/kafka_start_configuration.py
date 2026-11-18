"""Approved Kafka reading policies without broker client dependencies."""

from enum import StrEnum
from typing import ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class KafkaStartPosition(StrEnum):
    """Positions available when a partition has no saved starting boundary."""

    LATEST = "latest"
    EARLIEST = "earliest"


class KafkaOffsetGapPolicy(StrEnum):
    """Permitted responses to a missing or invalid established checkpoint."""

    FAIL = "fail"
    EARLIEST = "earliest"
    LATEST = "latest"


class KafkaStartConfiguration(SQLModel):
    """Reading defaults applied only when a new position decision is needed."""

    position: KafkaStartPosition = KafkaStartPosition.LATEST
    added_partition_position: KafkaStartPosition = KafkaStartPosition.EARLIEST
    offset_gap_policy: KafkaOffsetGapPolicy = KafkaOffsetGapPolicy.EARLIEST

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]
