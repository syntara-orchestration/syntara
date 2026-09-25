from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ErrorData")


@_attrs_define
class ErrorData:
    """RFC 9457 Problem Details format for error event data.
    This model is used for streaming error events and follows the RFC 9457 Problem Details specification. It provides
    machine-readable and human-readable error information with consistent structure.
    Attributes:
        type: URI reference identifying the problem type
        title: Short, human-readable summary of the problem
        detail: Human-readable explanation specific to this occurrence
        code: Machine-readable error code for programmatic handling
        retryable: Whether this error can be retried by creating a new invocation
        instance: Optional URI reference identifying the specific occurrence

        Attributes:
            type_ (str): URI reference identifying the problem type
            title (str): Short, human-readable summary of the problem
            detail (str): Human-readable explanation specific to this occurrence
            code (str): Machine-readable error code for programmatic handling
            retryable (bool): Whether this error can be retried by creating a new invocation
            instance (None | str | Unset): Optional URI reference identifying the specific occurrence
    """

    type_: str
    title: str
    detail: str
    code: str
    retryable: bool
    instance: None | str | Unset = UNSET
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

        error_data = cls(
            type_=type_,
            title=title,
            detail=detail,
            code=code,
            retryable=retryable,
            instance=instance,
        )

        error_data.additional_properties = d
        return error_data

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
