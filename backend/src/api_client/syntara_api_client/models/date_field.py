from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.date_value import DateValue


T = TypeVar("T", bound="DateField")


@_attrs_define
class DateField:
    """Date field collecting any combination of date, time, and timezone.

    Attributes:
        value_name (str):
        label (str):
        type_ (Literal['date']):
        placeholder (None | str | Unset):
        help_text (None | str | Unset):
        required (bool | Unset):  Default: False.
        include_date (bool | Unset): Collect a calendar date. Default: True.
        include_time (bool | Unset): Collect a 24-hour time. Requires include_timezone. Default: False.
        include_timezone (bool | Unset): Collect an IANA timezone name. Default: False.
        default (DateValue | None | Unset): Default value used when the responder submits nothing. Must supply exactly
            the included components.
    """

    value_name: str
    label: str
    type_: Literal["date"]
    placeholder: None | str | Unset = UNSET
    help_text: None | str | Unset = UNSET
    required: bool | Unset = False
    include_date: bool | Unset = True
    include_time: bool | Unset = False
    include_timezone: bool | Unset = False
    default: DateValue | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.date_value import DateValue

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

        include_date = self.include_date

        include_time = self.include_time

        include_timezone = self.include_timezone

        default: dict[str, Any] | None | Unset
        if isinstance(self.default, Unset):
            default = UNSET
        elif isinstance(self.default, DateValue):
            default = self.default.to_dict()
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
        if include_date is not UNSET:
            field_dict["include_date"] = include_date
        if include_time is not UNSET:
            field_dict["include_time"] = include_time
        if include_timezone is not UNSET:
            field_dict["include_timezone"] = include_timezone
        if default is not UNSET:
            field_dict["default"] = default

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.date_value import DateValue

        d = dict(src_dict)
        value_name = d.pop("value_name")

        label = d.pop("label")

        type_ = cast(Literal["date"], d.pop("type"))
        if type_ != "date":
            raise ValueError(f"type must match const 'date', got '{type_}'")

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

        include_date = d.pop("include_date", UNSET)

        include_time = d.pop("include_time", UNSET)

        include_timezone = d.pop("include_timezone", UNSET)

        def _parse_default(data: object) -> DateValue | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                default_type_0 = DateValue.from_dict(data)

                return default_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DateValue | None | Unset, data)

        default = _parse_default(d.pop("default", UNSET))

        date_field = cls(
            value_name=value_name,
            label=label,
            type_=type_,
            placeholder=placeholder,
            help_text=help_text,
            required=required,
            include_date=include_date,
            include_time=include_time,
            include_timezone=include_timezone,
            default=default,
        )

        return date_field
