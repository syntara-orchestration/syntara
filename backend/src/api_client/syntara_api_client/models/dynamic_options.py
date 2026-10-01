from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="DynamicOptions")


@_attrs_define
class DynamicOptions:
    """Dynamic option list resolved from upstream node output.

    Attributes:
        source (Literal['dynamic']):
        expression (str):
        value_key (None | str | Unset):
        label_key (None | str | Unset):
    """

    source: Literal["dynamic"]
    expression: str
    value_key: None | str | Unset = UNSET
    label_key: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        source = self.source

        expression = self.expression

        value_key: None | str | Unset
        if isinstance(self.value_key, Unset):
            value_key = UNSET
        else:
            value_key = self.value_key

        label_key: None | str | Unset
        if isinstance(self.label_key, Unset):
            label_key = UNSET
        else:
            label_key = self.label_key

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "source": source,
                "expression": expression,
            }
        )
        if value_key is not UNSET:
            field_dict["value_key"] = value_key
        if label_key is not UNSET:
            field_dict["label_key"] = label_key

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source = cast(Literal["dynamic"], d.pop("source"))
        if source != "dynamic":
            raise ValueError(f"source must match const 'dynamic', got '{source}'")

        expression = d.pop("expression")

        def _parse_value_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        value_key = _parse_value_key(d.pop("value_key", UNSET))

        def _parse_label_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        label_key = _parse_label_key(d.pop("label_key", UNSET))

        dynamic_options = cls(
            source=source,
            expression=expression,
            value_key=value_key,
            label_key=label_key,
        )

        return dynamic_options
