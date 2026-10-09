from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.credential_create_inputs import CredentialCreateInputs
    from ..models.credential_create_labels import CredentialCreateLabels


T = TypeVar("T", bound="CredentialCreate")


@_attrs_define
class CredentialCreate:
    """Schema for creating a new credential.

    Attributes:
        credential_type_id (UUID): ID of the credential type
        name (str): Human-readable credential name
        project_id (UUID): Project to assign credential to
        description (None | str | Unset): Optional description
        inputs (CredentialCreateInputs | Unset): Field values validated against type schema
        labels (CredentialCreateLabels | Unset): Key-value labels
    """

    credential_type_id: UUID
    name: str
    project_id: UUID
    description: None | str | Unset = UNSET
    inputs: CredentialCreateInputs | Unset = UNSET
    labels: CredentialCreateLabels | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        credential_type_id = str(self.credential_type_id)

        name = self.name

        project_id = str(self.project_id)

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
                "credential_type_id": credential_type_id,
                "name": name,
                "project_id": project_id,
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
        from ..models.credential_create_inputs import CredentialCreateInputs
        from ..models.credential_create_labels import CredentialCreateLabels

        d = dict(src_dict)
        credential_type_id = UUID(d.pop("credential_type_id"))

        name = d.pop("name")

        project_id = UUID(d.pop("project_id"))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        _inputs = d.pop("inputs", UNSET)
        inputs: CredentialCreateInputs | Unset
        if isinstance(_inputs, Unset):
            inputs = UNSET
        else:
            inputs = CredentialCreateInputs.from_dict(_inputs)

        _labels = d.pop("labels", UNSET)
        labels: CredentialCreateLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = CredentialCreateLabels.from_dict(_labels)

        credential_create = cls(
            credential_type_id=credential_type_id,
            name=name,
            project_id=project_id,
            description=description,
            inputs=inputs,
            labels=labels,
        )

        return credential_create
