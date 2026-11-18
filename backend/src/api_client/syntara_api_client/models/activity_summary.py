from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ActivitySummary")


@_attrs_define
class ActivitySummary:
    """Activity summary for workflow context.

    Passed through from the workflow engine as-is. Contains at minimum
    ``id``, ``name``, ``type``, and usually ``config`` with the full
    activity parameters so approvers can see what the step will do.

        Attributes:
            id (str): Activity ID from workflow definition
            name (str): Human-readable activity name
            type_ (str): Activity type (script_python, script_bash, approval, agentic, etc.)
    """

    id: str
    name: str
    type_: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        type_ = d.pop("type")

        activity_summary = cls(
            id=id,
            name=name,
            type_=type_,
        )

        activity_summary.additional_properties = d
        return activity_summary

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
