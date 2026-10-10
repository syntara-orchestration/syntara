from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.project_role_create_labels import ProjectRoleCreateLabels


T = TypeVar("T", bound="ProjectRoleCreate")


@_attrs_define
class ProjectRoleCreate:
    """Request body for creating a project-scoped role (project_id comes from URL path).

    Attributes:
        name (str):
        policies (list[str]):
        description (None | str | Unset):
        labels (ProjectRoleCreateLabels | Unset):
    """

    name: str
    policies: list[str]
    description: None | str | Unset = UNSET
    labels: ProjectRoleCreateLabels | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        policies = self.policies

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
                "policies": policies,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if labels is not UNSET:
            field_dict["labels"] = labels

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.project_role_create_labels import ProjectRoleCreateLabels

        d = dict(src_dict)
        name = d.pop("name")

        policies = cast(list[str], d.pop("policies"))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        _labels = d.pop("labels", UNSET)
        labels: ProjectRoleCreateLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = ProjectRoleCreateLabels.from_dict(_labels)

        project_role_create = cls(
            name=name,
            policies=policies,
            description=description,
            labels=labels,
        )

        return project_role_create
