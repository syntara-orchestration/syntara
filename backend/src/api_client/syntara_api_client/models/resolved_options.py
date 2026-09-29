from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.resolved_option import ResolvedOption


T = TypeVar("T", bound="ResolvedOptions")


@_attrs_define
class ResolvedOptions:
    """Dynamic options materialized into a concrete list at prompt creation.

    Produced only by the workflow engine, never authored. A form prompt is
    persisted with this shape so the responder view and submission membership
    validation operate on the same snapshot.

        Attributes:
            source (Literal['resolved']):
            values (list[ResolvedOption]):
    """

    source: Literal["resolved"]
    values: list[ResolvedOption]

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
        from ..models.resolved_option import ResolvedOption

        d = dict(src_dict)
        source = cast(Literal["resolved"], d.pop("source"))
        if source != "resolved":
            raise ValueError(f"source must match const 'resolved', got '{source}'")

        values = []
        _values = d.pop("values")
        for values_item_data in _values:
            values_item = ResolvedOption.from_dict(values_item_data)

            values.append(values_item)

        resolved_options = cls(
            source=source,
            values=values,
        )

        return resolved_options
