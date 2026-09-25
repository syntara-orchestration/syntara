from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.dynamic_options import DynamicOptions
    from ..models.static_options import StaticOptions


T = TypeVar("T", bound="MultiSelectField")


@_attrs_define
class MultiSelectField:
    """Multi-select field.

    Attributes:
        value_name (str):
        label (str):
        type_ (Literal['multi_select']):
        options (DynamicOptions | StaticOptions):
        placeholder (None | str | Unset):
        help_text (None | str | Unset):
        required (bool | Unset):  Default: False.
        default (list[Any] | None | Unset):
    """

    value_name: str
    label: str
    type_: Literal["multi_select"]
    options: DynamicOptions | StaticOptions
    placeholder: None | str | Unset = UNSET
    help_text: None | str | Unset = UNSET
    required: bool | Unset = False
    default: list[Any] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.static_options import StaticOptions

        value_name = self.value_name

        label = self.label

        type_ = self.type_

        options: dict[str, Any]
        if isinstance(self.options, StaticOptions):
            options = self.options.to_dict()
        else:
            options = self.options.to_dict()

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

        default: list[Any] | None | Unset
        if isinstance(self.default, Unset):
            default = UNSET
        elif isinstance(self.default, list):
            default = self.default

        else:
            default = self.default

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "value_name": value_name,
                "label": label,
                "type": type_,
                "options": options,
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
        from ..models.dynamic_options import DynamicOptions
        from ..models.static_options import StaticOptions

        d = dict(src_dict)
        value_name = d.pop("value_name")

        label = d.pop("label")

        type_ = cast(Literal["multi_select"], d.pop("type"))
        if type_ != "multi_select":
            raise ValueError(f"type must match const 'multi_select', got '{type_}'")

        def _parse_options(data: object) -> DynamicOptions | StaticOptions:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                options_type_0 = StaticOptions.from_dict(data)

                return options_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            options_type_1 = DynamicOptions.from_dict(data)

            return options_type_1

        options = _parse_options(d.pop("options"))

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

        def _parse_default(data: object) -> list[Any] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                default_type_0 = cast(list[Any], data)

                return default_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | None | Unset, data)

        default = _parse_default(d.pop("default", UNSET))

        multi_select_field = cls(
            value_name=value_name,
            label=label,
            type_=type_,
            options=options,
            placeholder=placeholder,
            help_text=help_text,
            required=required,
            default=default,
        )

        return multi_select_field
