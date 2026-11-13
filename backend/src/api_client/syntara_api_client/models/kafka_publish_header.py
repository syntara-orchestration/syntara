from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.kafka_encoded_value import KafkaEncodedValue


T = TypeVar("T", bound="KafkaPublishHeader")


@_attrs_define
class KafkaPublishHeader:
    """One ordered header; duplicate names and null values are intentional.

    Attributes:
        name (str):
        value (KafkaEncodedValue | None):
    """

    name: str
    value: KafkaEncodedValue | None

    def to_dict(self) -> dict[str, Any]:
        from ..models.kafka_encoded_value import KafkaEncodedValue

        name = self.name

        value: dict[str, Any] | None
        if isinstance(self.value, KafkaEncodedValue):
            value = self.value.to_dict()
        else:
            value = self.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "value": value,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.kafka_encoded_value import KafkaEncodedValue

        d = dict(src_dict)
        name = d.pop("name")

        def _parse_value(data: object) -> KafkaEncodedValue | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                value_type_0 = KafkaEncodedValue.from_dict(data)

                return value_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(KafkaEncodedValue | None, data)

        value = _parse_value(d.pop("value"))

        kafka_publish_header = cls(
            name=name,
            value=value,
        )

        return kafka_publish_header
