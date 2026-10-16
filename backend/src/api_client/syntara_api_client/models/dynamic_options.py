from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="DynamicOptions")


@_attrs_define
class DynamicOptions:
    """Dynamic option list resolved from a non-empty array of upstream objects.

    Each object must contain a string label and scalar value at the required
    ``label_key`` and ``value_key``.

        Attributes:
            source (Literal['dynamic']):
            expression (str): Template expression resolving to a non-empty array of objects. Each object must contain a
                string label and scalar value at the required 'label_key' and 'value_key'.
            value_key (str): Required object key containing the typed option value.
            label_key (str): Required object key containing the option label.
    """

    source: Literal["dynamic"]
    expression: str
    value_key: str
    label_key: str

    def to_dict(self) -> dict[str, Any]:
        source = self.source

        expression = self.expression

        value_key = self.value_key

        label_key = self.label_key

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "source": source,
                "expression": expression,
                "value_key": value_key,
                "label_key": label_key,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source = cast(Literal["dynamic"], d.pop("source"))
        if source != "dynamic":
            raise ValueError(f"source must match const 'dynamic', got '{source}'")

        expression = d.pop("expression")

        value_key = d.pop("value_key")

        label_key = d.pop("label_key")

        dynamic_options = cls(
            source=source,
            expression=expression,
            value_key=value_key,
            label_key=label_key,
        )

        return dynamic_options
