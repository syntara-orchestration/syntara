from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.project_credential_create_inputs import ProjectCredentialCreateInputs
    from ..models.project_credential_create_labels import ProjectCredentialCreateLabels


T = TypeVar("T", bound="ProjectCredentialCreate")


@_attrs_define
class ProjectCredentialCreate:
    """Schema for creating a credential via a project-scoped endpoint (project_id from URL path).

    Attributes:
        name (str): Human-readable credential name
        credential_type_id (UUID): ID of the credential type
        description (None | str | Unset): Optional description
        inputs (ProjectCredentialCreateInputs | Unset): Field values validated against type schema
        labels (ProjectCredentialCreateLabels | Unset): Key-value labels
    """

    name: str
    credential_type_id: UUID
    description: None | str | Unset = UNSET
    inputs: ProjectCredentialCreateInputs | Unset = UNSET
    labels: ProjectCredentialCreateLabels | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        credential_type_id = str(self.credential_type_id)

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        inputs: dict[str, Any] | Unset = UNSET
        if not isinstance(self.inputs, Unset):
            inputs = self.inputs.to_dict()

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "credential_type_id": credential_type_id,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if inputs is not UNSET:
            field_dict["inputs"] = inputs
        if labels is not UNSET:
            field_dict["labels"] = labels

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.project_credential_create_inputs import ProjectCredentialCreateInputs
        from ..models.project_credential_create_labels import ProjectCredentialCreateLabels

        d = dict(src_dict)
        name = d.pop("name")

        credential_type_id = UUID(d.pop("credential_type_id"))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        _inputs = d.pop("inputs", UNSET)
        inputs: ProjectCredentialCreateInputs | Unset
        if isinstance(_inputs, Unset):
            inputs = UNSET
        else:
            inputs = ProjectCredentialCreateInputs.from_dict(_inputs)

        _labels = d.pop("labels", UNSET)
        labels: ProjectCredentialCreateLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = ProjectCredentialCreateLabels.from_dict(_labels)

        project_credential_create = cls(
            name=name,
            credential_type_id=credential_type_id,
            description=description,
            inputs=inputs,
            labels=labels,
        )

        return project_credential_create
