from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="FormFieldErrorResponse")


@_attrs_define
class FormFieldErrorResponse:
    """Structured validation error for one submitted form field.

    Attributes:
        field (str): Submitted field name
        label (str): Display label for the field
        code (str): Machine-readable validation error code
        message (str): User-facing validation message
    """

    field: str
    label: str
    code: str
    message: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        field = self.field

        label = self.label

        code = self.code

        message = self.message

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "field": field,
                "label": label,
                "code": code,
                "message": message,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        field = d.pop("field")

        label = d.pop("label")

        code = d.pop("code")

        message = d.pop("message")

        form_field_error_response = cls(
            field=field,
            label=label,
            code=code,
            message=message,
        )

        form_field_error_response.additional_properties = d
        return form_field_error_response

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
