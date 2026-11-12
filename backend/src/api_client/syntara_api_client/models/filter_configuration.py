from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="FilterConfiguration")


@_attrs_define
class FilterConfiguration:
    """One original CEL expression, with no implicit conditions or field grouping.

    Empty or whitespace-only expressions mean no filter. Publication validates
    syntax, names and statically known boolean types; dynamic types are checked
    during evaluation. The original non-empty expression is preserved unchanged.

        Attributes:
            expression (str): Complete CEL expression (maximum 16,384 characters).
    """

    expression: str

    def to_dict(self) -> dict[str, Any]:
        expression = self.expression

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "expression": expression,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        expression = d.pop("expression")

        filter_configuration = cls(
            expression=expression,
        )

        return filter_configuration
