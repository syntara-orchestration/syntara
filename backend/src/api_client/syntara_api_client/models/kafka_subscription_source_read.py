from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="KafkaSubscriptionSourceRead")


@_attrs_define
class KafkaSubscriptionSourceRead:
    """Effective Kafka group for the current, non-retired subscription source.

    Attributes:
        trigger_node_id (str):
        source_id (UUID):
        generation (int):
        configuration_revision (int):
        integration_id (UUID):
        topic (str):
        group_id (str):
        group_id_is_generated (bool): Whether the effective group is the automatic ID for this source identity.
    """

    trigger_node_id: str
    source_id: UUID
    generation: int
    configuration_revision: int
    integration_id: UUID
    topic: str
    group_id: str
    group_id_is_generated: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trigger_node_id = self.trigger_node_id

        source_id = str(self.source_id)

        generation = self.generation

        configuration_revision = self.configuration_revision

        integration_id = str(self.integration_id)

        topic = self.topic

        group_id = self.group_id

        group_id_is_generated = self.group_id_is_generated

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trigger_node_id": trigger_node_id,
                "source_id": source_id,
                "generation": generation,
                "configuration_revision": configuration_revision,
                "integration_id": integration_id,
                "topic": topic,
                "group_id": group_id,
                "group_id_is_generated": group_id_is_generated,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        trigger_node_id = d.pop("trigger_node_id")

        source_id = UUID(d.pop("source_id"))

        generation = d.pop("generation")

        configuration_revision = d.pop("configuration_revision")

        integration_id = UUID(d.pop("integration_id"))

        topic = d.pop("topic")

        group_id = d.pop("group_id")

        group_id_is_generated = d.pop("group_id_is_generated")

        kafka_subscription_source_read = cls(
            trigger_node_id=trigger_node_id,
            source_id=source_id,
            generation=generation,
            configuration_revision=configuration_revision,
            integration_id=integration_id,
            topic=topic,
            group_id=group_id,
            group_id_is_generated=group_id_is_generated,
        )

        kafka_subscription_source_read.additional_properties = d
        return kafka_subscription_source_read

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
