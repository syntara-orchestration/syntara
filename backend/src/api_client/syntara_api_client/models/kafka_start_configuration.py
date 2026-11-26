from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.kafka_offset_gap_policy import KafkaOffsetGapPolicy
from ..models.kafka_start_position import KafkaStartPosition
from ..types import UNSET, Unset

T = TypeVar("T", bound="KafkaStartConfiguration")


@_attrs_define
class KafkaStartConfiguration:
    """Reading defaults applied only when a new position decision is needed.

    Attributes:
        position (KafkaStartPosition | Unset): Positions available when a partition has no saved starting boundary.
        added_partition_position (KafkaStartPosition | Unset): Positions available when a partition has no saved
            starting boundary.
        offset_gap_policy (KafkaOffsetGapPolicy | Unset): Permitted responses to a missing or invalid established
            checkpoint.
    """

    position: KafkaStartPosition | Unset = UNSET
    added_partition_position: KafkaStartPosition | Unset = UNSET
    offset_gap_policy: KafkaOffsetGapPolicy | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        position: str | Unset = UNSET
        if not isinstance(self.position, Unset):
            position = self.position.value

        added_partition_position: str | Unset = UNSET
        if not isinstance(self.added_partition_position, Unset):
            added_partition_position = self.added_partition_position.value

        offset_gap_policy: str | Unset = UNSET
        if not isinstance(self.offset_gap_policy, Unset):
            offset_gap_policy = self.offset_gap_policy.value

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if position is not UNSET:
            field_dict["position"] = position
        if added_partition_position is not UNSET:
            field_dict["added_partition_position"] = added_partition_position
        if offset_gap_policy is not UNSET:
            field_dict["offset_gap_policy"] = offset_gap_policy

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        _position = d.pop("position", UNSET)
        position: KafkaStartPosition | Unset
        if isinstance(_position, Unset):
            position = UNSET
        else:
            position = KafkaStartPosition(_position)

        _added_partition_position = d.pop("added_partition_position", UNSET)
        added_partition_position: KafkaStartPosition | Unset
        if isinstance(_added_partition_position, Unset):
            added_partition_position = UNSET
        else:
            added_partition_position = KafkaStartPosition(_added_partition_position)

        _offset_gap_policy = d.pop("offset_gap_policy", UNSET)
        offset_gap_policy: KafkaOffsetGapPolicy | Unset
        if isinstance(_offset_gap_policy, Unset):
            offset_gap_policy = UNSET
        else:
            offset_gap_policy = KafkaOffsetGapPolicy(_offset_gap_policy)

        kafka_start_configuration = cls(
            position=position,
            added_partition_position=added_partition_position,
            offset_gap_policy=offset_gap_policy,
        )

        return kafka_start_configuration
