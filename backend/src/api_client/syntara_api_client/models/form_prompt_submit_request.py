from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.form_prompt_submit_request_response_data import FormPromptSubmitRequestResponseData


T = TypeVar("T", bound="FormPromptSubmitRequest")


@_attrs_define
class FormPromptSubmitRequest:
    """Request payload for submitting a response to a form prompt.

    Attributes:
        response_data (FormPromptSubmitRequestResponseData): Submitted form field values, keyed by field name
    """

    response_data: FormPromptSubmitRequestResponseData
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        response_data = self.response_data.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "response_data": response_data,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.form_prompt_submit_request_response_data import FormPromptSubmitRequestResponseData

        d = dict(src_dict)
        response_data = FormPromptSubmitRequestResponseData.from_dict(d.pop("response_data"))

        form_prompt_submit_request = cls(
            response_data=response_data,
        )

        form_prompt_submit_request.additional_properties = d
        return form_prompt_submit_request

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
