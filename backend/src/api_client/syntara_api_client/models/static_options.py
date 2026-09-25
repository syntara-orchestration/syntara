from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.static_option import StaticOption


T = TypeVar("T", bound="StaticOptions")


@_attrs_define
class StaticOptions:
    """Static option list for dropdown or multi-select.

    Attributes:
        source (Literal['static']):
        values (list[StaticOption]):
    """

    source: Literal["static"]
    values: list[StaticOption]

    def to_dict(self) -> dict[str, Any]:
        source = self.source

        values = []
        for values_item_data in self.values:
            values_item = values_item_data.to_dict()
            values.append(values_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "source": source,
                "values": values,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.static_option import StaticOption

        d = dict(src_dict)
        source = cast(Literal["static"], d.pop("source"))
        if source != "static":
            raise ValueError(f"source must match const 'static', got '{source}'")

        values = []
        _values = d.pop("values")
        for values_item_data in _values:
            values_item = StaticOption.from_dict(values_item_data)

            values.append(values_item)

        static_options = cls(
            source=source,
            values=values,
        )

        return static_options
