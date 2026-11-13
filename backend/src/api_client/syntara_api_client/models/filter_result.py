from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.filter_error_code import FilterErrorCode
from ..models.filter_outcome import FilterOutcome
from ..types import UNSET, Unset

T = TypeVar("T", bound="FilterResult")


@_attrs_define
class FilterResult:
    """One evaluation result; callers own any delivery or audit effects.

    Attributes:
        outcome (FilterOutcome): Content decisions without persistence or acknowledgement authority.
        error_code (FilterErrorCode | None | Unset):
    """

    outcome: FilterOutcome
    error_code: FilterErrorCode | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        outcome = self.outcome.value

        error_code: None | str | Unset
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        elif isinstance(self.error_code, FilterErrorCode):
            error_code = self.error_code.value
        else:
            error_code = self.error_code

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "outcome": outcome,
            }
        )
        if error_code is not UNSET:
            field_dict["error_code"] = error_code

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        outcome = FilterOutcome(d.pop("outcome"))

        def _parse_error_code(data: object) -> FilterErrorCode | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                error_code_type_0 = FilterErrorCode(data)

                return error_code_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FilterErrorCode | None | Unset, data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        filter_result = cls(
            outcome=outcome,
            error_code=error_code,
        )

        return filter_result
