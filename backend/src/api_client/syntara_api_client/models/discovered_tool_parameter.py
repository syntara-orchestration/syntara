from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="DiscoveredToolParameter")


@_attrs_define
class DiscoveredToolParameter:
    """A parameter belonging to a discovered tool.

    Attributes:
        name (str):
        type_ (str | Unset):  Default: 'string'.
        description (str | Unset):  Default: ''.
        required (bool | Unset):  Default: False.
    """

    name: str
    type_: str | Unset = "string"
    description: str | Unset = ""
    required: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        type_ = self.type_

        description = self.description

        required = self.required

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_
        if description is not UNSET:
            field_dict["description"] = description
        if required is not UNSET:
            field_dict["required"] = required

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        type_ = d.pop("type", UNSET)

        description = d.pop("description", UNSET)

        required = d.pop("required", UNSET)

        discovered_tool_parameter = cls(
            name=name,
            type_=type_,
            description=description,
            required=required,
        )

        return discovered_tool_parameter
