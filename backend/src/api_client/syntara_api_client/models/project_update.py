from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.project_update_labels_type_0 import ProjectUpdateLabelsType0


T = TypeVar("T", bound="ProjectUpdate")


@_attrs_define
class ProjectUpdate:
    """Request body for updating a project.

    Attributes:
        name (None | str | Unset):
        description (None | str | Unset):
        labels (None | ProjectUpdateLabelsType0 | Unset):
    """

    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    labels: None | ProjectUpdateLabelsType0 | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.project_update_labels_type_0 import ProjectUpdateLabelsType0

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        labels: dict[str, Any] | None | Unset
        if isinstance(self.labels, Unset):
            labels = UNSET
        elif isinstance(self.labels, ProjectUpdateLabelsType0):
            labels = self.labels.to_dict()
        else:
            labels = self.labels

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if description is not UNSET:
            field_dict["description"] = description
        if labels is not UNSET:
            field_dict["labels"] = labels

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.project_update_labels_type_0 import ProjectUpdateLabelsType0

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_labels(data: object) -> None | ProjectUpdateLabelsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                labels_type_0 = ProjectUpdateLabelsType0.from_dict(data)

                return labels_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ProjectUpdateLabelsType0 | Unset, data)

        labels = _parse_labels(d.pop("labels", UNSET))

        project_update = cls(
            name=name,
            description=description,
            labels=labels,
        )

        return project_update
