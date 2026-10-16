from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="NumberField")


@_attrs_define
class NumberField:
    """Numeric field supporting int or float.

    Attributes:
        value_name (str):
        label (str):
        type_ (Literal['number']):
        placeholder (None | str | Unset):
        help_text (None | str | Unset):
        required (bool | Unset):  Default: False.
        default (float | int | None | Unset):
    """

    value_name: str
    label: str
    type_: Literal["number"]
    placeholder: None | str | Unset = UNSET
    help_text: None | str | Unset = UNSET
    required: bool | Unset = False
    default: float | int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        value_name = self.value_name

        label = self.label

        type_ = self.type_

        placeholder: None | str | Unset
        if isinstance(self.placeholder, Unset):
            placeholder = UNSET
        else:
            placeholder = self.placeholder

        help_text: None | str | Unset
        if isinstance(self.help_text, Unset):
            help_text = UNSET
        else:
            help_text = self.help_text

        required = self.required

        default: float | int | None | Unset
        if isinstance(self.default, Unset):
            default = UNSET
        else:
            default = self.default

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "value_name": value_name,
                "label": label,
                "type": type_,
            }
        )
        if placeholder is not UNSET:
            field_dict["placeholder"] = placeholder
        if help_text is not UNSET:
            field_dict["help_text"] = help_text
        if required is not UNSET:
            field_dict["required"] = required
        if default is not UNSET:
            field_dict["default"] = default

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        value_name = d.pop("value_name")

        label = d.pop("label")

        type_ = cast(Literal["number"], d.pop("type"))
        if type_ != "number":
            raise ValueError(f"type must match const 'number', got '{type_}'")

        def _parse_placeholder(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        placeholder = _parse_placeholder(d.pop("placeholder", UNSET))

        def _parse_help_text(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        help_text = _parse_help_text(d.pop("help_text", UNSET))

        required = d.pop("required", UNSET)

        def _parse_default(data: object) -> float | int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | int | None | Unset, data)

        default = _parse_default(d.pop("default", UNSET))

        number_field = cls(
            value_name=value_name,
            label=label,
            type_=type_,
            placeholder=placeholder,
            help_text=help_text,
            required=required,
            default=default,
        )

        return number_field
