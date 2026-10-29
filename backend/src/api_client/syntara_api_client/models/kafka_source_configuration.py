from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="KafkaSourceConfiguration")


@_attrs_define
class KafkaSourceConfiguration:
    """Fixed Kafka source address for one source generation; no secrets or payloads.

    ``topic`` and the generated ``group_id`` are immutable within a generation.
    ``cluster_id`` and ``topic_id`` are populated once during verified
    initialization where the broker exposes them; an identity change creates a
    new generation rather than mutating these fields.

        Attributes:
            topic (str):
            group_id (str):
            transport (Literal['kafka'] | Unset):  Default: 'kafka'.
            cluster_id (None | str | Unset):
            topic_id (None | str | Unset):
            initial_partition_ids (list[int] | None | Unset): System-managed first verified topic partition set; absent
                until captured
    """

    topic: str
    group_id: str
    transport: Literal["kafka"] | Unset = "kafka"
    cluster_id: None | str | Unset = UNSET
    topic_id: None | str | Unset = UNSET
    initial_partition_ids: list[int] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        topic = self.topic

        group_id = self.group_id

        transport = self.transport

        cluster_id: None | str | Unset
        if isinstance(self.cluster_id, Unset):
            cluster_id = UNSET
        else:
            cluster_id = self.cluster_id

        topic_id: None | str | Unset
        if isinstance(self.topic_id, Unset):
            topic_id = UNSET
        else:
            topic_id = self.topic_id

        initial_partition_ids: list[int] | None | Unset
        if isinstance(self.initial_partition_ids, Unset):
            initial_partition_ids = UNSET
        elif isinstance(self.initial_partition_ids, list):
            initial_partition_ids = self.initial_partition_ids

        else:
            initial_partition_ids = self.initial_partition_ids

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "topic": topic,
                "group_id": group_id,
            }
        )
        if transport is not UNSET:
            field_dict["transport"] = transport
        if cluster_id is not UNSET:
            field_dict["cluster_id"] = cluster_id
        if topic_id is not UNSET:
            field_dict["topic_id"] = topic_id
        if initial_partition_ids is not UNSET:
            field_dict["initial_partition_ids"] = initial_partition_ids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        topic = d.pop("topic")

        group_id = d.pop("group_id")

        transport = cast(Literal["kafka"] | Unset, d.pop("transport", UNSET))
        if transport != "kafka" and not isinstance(transport, Unset):
            raise ValueError(f"transport must match const 'kafka', got '{transport}'")

        def _parse_cluster_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cluster_id = _parse_cluster_id(d.pop("cluster_id", UNSET))

        def _parse_topic_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        topic_id = _parse_topic_id(d.pop("topic_id", UNSET))

        def _parse_initial_partition_ids(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                initial_partition_ids_type_0 = cast(list[int], data)

                return initial_partition_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        initial_partition_ids = _parse_initial_partition_ids(d.pop("initial_partition_ids", UNSET))

        kafka_source_configuration = cls(
            topic=topic,
            group_id=group_id,
            transport=transport,
            cluster_id=cluster_id,
            topic_id=topic_id,
            initial_partition_ids=initial_partition_ids,
        )

        return kafka_source_configuration
