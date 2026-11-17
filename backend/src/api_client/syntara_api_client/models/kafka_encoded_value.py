from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.kafka_encoded_value_encoding import KafkaEncodedValueEncoding

T = TypeVar("T", bound="KafkaEncodedValue")


@_attrs_define
class KafkaEncodedValue:
    """Explicit text or binary representation; empty bytes remain distinct from null.

    Attributes:
        encoding (KafkaEncodedValueEncoding):
        value (str):
    """

    encoding: KafkaEncodedValueEncoding
    value: str

    def to_dict(self) -> dict[str, Any]:
        encoding = self.encoding.value

        value = self.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "encoding": encoding,
                "value": value,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        encoding = KafkaEncodedValueEncoding(d.pop("encoding"))

        value = d.pop("value")

        kafka_encoded_value = cls(
            encoding=encoding,
            value=value,
        )

        return kafka_encoded_value
