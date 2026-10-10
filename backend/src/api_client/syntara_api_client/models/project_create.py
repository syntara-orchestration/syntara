from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.project_create_labels import ProjectCreateLabels


T = TypeVar("T", bound="ProjectCreate")


@_attrs_define
class ProjectCreate:
    """Request body for creating a project.

    Attributes:
        name (str):
        description (None | str | Unset):
        labels (ProjectCreateLabels | Unset):
    """

    name: str
    description: None | str | Unset = UNSET
    labels: ProjectCreateLabels | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if labels is not UNSET:
            field_dict["labels"] = labels

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.project_create_labels import ProjectCreateLabels

        d = dict(src_dict)
        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        _labels = d.pop("labels", UNSET)
        labels: ProjectCreateLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = ProjectCreateLabels.from_dict(_labels)

        project_create = cls(
            name=name,
            description=description,
            labels=labels,
        )

        return project_create
