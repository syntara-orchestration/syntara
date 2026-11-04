from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="StaticOption")


@_attrs_define
class StaticOption:
    """A single static option for dropdown or multi-select.

    Attributes:
        display_label (str):
        value (str):
    """

    display_label: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        display_label = self.display_label

        value = self.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "display_label": display_label,
                "value": value,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        display_label = d.pop("display_label")

        value = d.pop("value")

        static_option = cls(
            display_label=display_label,
            value=value,
        )

        return static_option
