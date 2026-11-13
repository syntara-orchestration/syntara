from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="FilterTestRequest")


@_attrs_define
class FilterTestRequest:
    """An optional CEL expression and required JSON bound directly as input.

    Omitted, empty and whitespace-only expressions mean no filter. No Kafka
    decoding, input restructuring or payload-schema validation is performed.

        Attributes:
            input_ (Any):
            expression (None | str | Unset): Complete CEL expression (maximum 16,384 characters).
    """

    input_: Any
    expression: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        input_ = self.input_

        expression: None | str | Unset
        if isinstance(self.expression, Unset):
            expression = UNSET
        else:
            expression = self.expression

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "input": input_,
            }
        )
        if expression is not UNSET:
            field_dict["expression"] = expression

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        input_ = d.pop("input")

        def _parse_expression(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        expression = _parse_expression(d.pop("expression", UNSET))

        filter_test_request = cls(
            input_=input_,
            expression=expression,
        )

        return filter_test_request
