from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="WorkflowVersionUpdate")


@_attrs_define
class WorkflowVersionUpdate:
    """Request body for updating version metadata (PATCH /workflows/{id}/versions/{version}).

    Attributes:
        name (None | str | Unset): Version name
        change_description (None | str | Unset): Description of changes
    """

    name: None | str | Unset = UNSET
    change_description: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        change_description: None | str | Unset
        if isinstance(self.change_description, Unset):
            change_description = UNSET
        else:
            change_description = self.change_description

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if change_description is not UNSET:
            field_dict["change_description"] = change_description

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_change_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        change_description = _parse_change_description(d.pop("change_description", UNSET))

        workflow_version_update = cls(
            name=name,
            change_description=change_description,
        )

        return workflow_version_update
