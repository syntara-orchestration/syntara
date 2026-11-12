from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="FilterValidationProblem")


@_attrs_define
class FilterValidationProblem:
    """Invalid CEL with a safe category and optional one-based compiler location.

    Attributes:
        type_ (str): URI reference identifying the problem type
        title (str): Short, human-readable summary of the problem
        detail (str): Human-readable explanation specific to this occurrence
        code (str): Machine-readable error code for programmatic handling
        retryable (bool): Whether this error can be retried by creating a new invocation
        instance (None | str | Unset): Optional URI reference identifying the specific occurrence
        line (int | None | Unset): One-based compiler source line, when available
        column (int | None | Unset): One-based compiler source column, when available
    """

    type_: str
    title: str
    detail: str
    code: str
    retryable: bool
    instance: None | str | Unset = UNSET
    line: int | None | Unset = UNSET
    column: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        title = self.title

        detail = self.detail

        code = self.code

        retryable = self.retryable

        instance: None | str | Unset
        if isinstance(self.instance, Unset):
            instance = UNSET
        else:
            instance = self.instance

        line: int | None | Unset
        if isinstance(self.line, Unset):
            line = UNSET
        else:
            line = self.line

        column: int | None | Unset
        if isinstance(self.column, Unset):
            column = UNSET
        else:
            column = self.column

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "title": title,
                "detail": detail,
                "code": code,
                "retryable": retryable,
            }
        )
        if instance is not UNSET:
            field_dict["instance"] = instance
        if line is not UNSET:
            field_dict["line"] = line
        if column is not UNSET:
            field_dict["column"] = column

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = d.pop("type")

        title = d.pop("title")

        detail = d.pop("detail")

        code = d.pop("code")

        retryable = d.pop("retryable")

        def _parse_instance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance = _parse_instance(d.pop("instance", UNSET))

        def _parse_line(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        line = _parse_line(d.pop("line", UNSET))

        def _parse_column(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        column = _parse_column(d.pop("column", UNSET))

        filter_validation_problem = cls(
            type_=type_,
            title=title,
            detail=detail,
            code=code,
            retryable=retryable,
            instance=instance,
            line=line,
            column=column,
        )

        filter_validation_problem.additional_properties = d
        return filter_validation_problem

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
