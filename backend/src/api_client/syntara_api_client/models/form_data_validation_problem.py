from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.form_field_error_response import FormFieldErrorResponse


T = TypeVar("T", bound="FormDataValidationProblem")


@_attrs_define
class FormDataValidationProblem:
    """RFC 9457 form validation problem with per-field error details.

    Attributes:
        type_ (str): URI reference identifying the problem type
        title (str): Short, human-readable summary of the problem
        detail (str): Human-readable explanation specific to this occurrence
        code (str): Machine-readable error code for programmatic handling
        retryable (bool): Whether this error can be retried by creating a new invocation
        errors (list[FormFieldErrorResponse]): Per-field validation errors
        instance (None | str | Unset): Optional URI reference identifying the specific occurrence
    """

    type_: str
    title: str
    detail: str
    code: str
    retryable: bool
    errors: list[FormFieldErrorResponse]
    instance: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        title = self.title

        detail = self.detail

        code = self.code

        retryable = self.retryable

        errors = []
        for errors_item_data in self.errors:
            errors_item = errors_item_data.to_dict()
            errors.append(errors_item)

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
                "errors": errors,
            }
        )
        if instance is not UNSET:
            field_dict["instance"] = instance

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.form_field_error_response import FormFieldErrorResponse

        d = dict(src_dict)
        type_ = d.pop("type")

        title = d.pop("title")

        detail = d.pop("detail")

        code = d.pop("code")

        retryable = d.pop("retryable")

        errors = []
        _errors = d.pop("errors")
        for errors_item_data in _errors:
            errors_item = FormFieldErrorResponse.from_dict(errors_item_data)

            errors.append(errors_item)

        def _parse_instance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance = _parse_instance(d.pop("instance", UNSET))

        form_data_validation_problem = cls(
            type_=type_,
            title=title,
            detail=detail,
            code=code,
            retryable=retryable,
            errors=errors,
            instance=instance,
        )

        form_data_validation_problem.additional_properties = d
        return form_data_validation_problem

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
