from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.checkbox_field import CheckboxField
    from ..models.date_field import DateField
    from ..models.dropdown_field import DropdownField
    from ..models.email_field import EmailField
    from ..models.masked_text_field import MaskedTextField
    from ..models.multi_select_field import MultiSelectField
    from ..models.number_field import NumberField
    from ..models.text_area_field import TextAreaField
    from ..models.text_field import TextField


T = TypeVar("T", bound="FormDefinition")


@_attrs_define
class FormDefinition:
    """Complete form definition with fields and metadata.

    Attributes:
        fields (list[CheckboxField | DateField | DropdownField | EmailField | MaskedTextField | MultiSelectField |
            NumberField | TextAreaField | TextField]):
    """

    fields: list[
        CheckboxField
        | DateField
        | DropdownField
        | EmailField
        | MaskedTextField
        | MultiSelectField
        | NumberField
        | TextAreaField
        | TextField
    ]

    def to_dict(self) -> dict[str, Any]:
        from ..models.checkbox_field import CheckboxField
        from ..models.date_field import DateField
        from ..models.dropdown_field import DropdownField
        from ..models.email_field import EmailField
        from ..models.masked_text_field import MaskedTextField
        from ..models.number_field import NumberField
        from ..models.text_area_field import TextAreaField
        from ..models.text_field import TextField

        fields = []
        for fields_item_data in self.fields:
            fields_item: dict[str, Any]
            if isinstance(fields_item_data, TextField):
                fields_item = fields_item_data.to_dict()
            elif isinstance(fields_item_data, TextAreaField):
                fields_item = fields_item_data.to_dict()
            elif isinstance(fields_item_data, MaskedTextField):
                fields_item = fields_item_data.to_dict()
            elif isinstance(fields_item_data, EmailField):
                fields_item = fields_item_data.to_dict()
            elif isinstance(fields_item_data, NumberField):
                fields_item = fields_item_data.to_dict()
            elif isinstance(fields_item_data, CheckboxField):
                fields_item = fields_item_data.to_dict()
            elif isinstance(fields_item_data, DateField):
                fields_item = fields_item_data.to_dict()
            elif isinstance(fields_item_data, DropdownField):
                fields_item = fields_item_data.to_dict()
            else:
                fields_item = fields_item_data.to_dict()

            fields.append(fields_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "fields": fields,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.checkbox_field import CheckboxField
        from ..models.date_field import DateField
        from ..models.dropdown_field import DropdownField
        from ..models.email_field import EmailField
        from ..models.masked_text_field import MaskedTextField
        from ..models.multi_select_field import MultiSelectField
        from ..models.number_field import NumberField
        from ..models.text_area_field import TextAreaField
        from ..models.text_field import TextField

        d = dict(src_dict)
        fields = []
        _fields = d.pop("fields")
        for fields_item_data in _fields:

            def _parse_fields_item(
                data: object,
            ) -> (
                CheckboxField
                | DateField
                | DropdownField
                | EmailField
                | MaskedTextField
                | MultiSelectField
                | NumberField
                | TextAreaField
                | TextField
            ):
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    fields_item_type_0 = TextField.from_dict(data)

                    return fields_item_type_0
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    fields_item_type_1 = TextAreaField.from_dict(data)

                    return fields_item_type_1
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    fields_item_type_2 = MaskedTextField.from_dict(data)

                    return fields_item_type_2
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    fields_item_type_3 = EmailField.from_dict(data)

                    return fields_item_type_3
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    fields_item_type_4 = NumberField.from_dict(data)

                    return fields_item_type_4
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    fields_item_type_5 = CheckboxField.from_dict(data)

                    return fields_item_type_5
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    fields_item_type_6 = DateField.from_dict(data)

                    return fields_item_type_6
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    fields_item_type_7 = DropdownField.from_dict(data)

                    return fields_item_type_7
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                if not isinstance(data, dict):
                    raise TypeError()
                fields_item_type_8 = MultiSelectField.from_dict(data)

                return fields_item_type_8

            fields_item = _parse_fields_item(fields_item_data)

            fields.append(fields_item)

        form_definition = cls(
            fields=fields,
        )

        return form_definition
