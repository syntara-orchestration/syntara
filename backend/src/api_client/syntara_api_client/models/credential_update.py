from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.credential_update_inputs_type_0 import CredentialUpdateInputsType0
    from ..models.credential_update_labels_type_0 import CredentialUpdateLabelsType0


T = TypeVar("T", bound="CredentialUpdate")


@_attrs_define
class CredentialUpdate:
    """Schema for partially updating a credential. $encrypted$ preserves existing values.

    Attributes:
        description (None | str | Unset):
        enabled (bool | None | Unset):
        inputs (CredentialUpdateInputsType0 | None | Unset):
        labels (CredentialUpdateLabelsType0 | None | Unset):
        name (None | str | Unset):
        project_id (None | Unset | UUID): Project ID (immutable after creation; rejected if different from stored value)
    """

    description: None | str | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    inputs: CredentialUpdateInputsType0 | None | Unset = UNSET
    labels: CredentialUpdateLabelsType0 | None | Unset = UNSET
    name: None | str | Unset = UNSET
    project_id: None | Unset | UUID = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.credential_update_inputs_type_0 import CredentialUpdateInputsType0
        from ..models.credential_update_labels_type_0 import CredentialUpdateLabelsType0

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        inputs: dict[str, Any] | None | Unset
        if isinstance(self.inputs, Unset):
            inputs = UNSET
        elif isinstance(self.inputs, CredentialUpdateInputsType0):
            inputs = self.inputs.to_dict()
        else:
            inputs = self.inputs

        labels: dict[str, Any] | None | Unset
        if isinstance(self.labels, Unset):
            labels = UNSET
        elif isinstance(self.labels, CredentialUpdateLabelsType0):
            labels = self.labels.to_dict()
        else:
            labels = self.labels

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        project_id: None | str | Unset
        if isinstance(self.project_id, Unset):
            project_id = UNSET
        elif isinstance(self.project_id, UUID):
            project_id = str(self.project_id)
        else:
            project_id = self.project_id

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if description is not UNSET:
            field_dict["description"] = description
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if inputs is not UNSET:
            field_dict["inputs"] = inputs
        if labels is not UNSET:
            field_dict["labels"] = labels
        if name is not UNSET:
            field_dict["name"] = name
        if project_id is not UNSET:
            field_dict["project_id"] = project_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.credential_update_inputs_type_0 import CredentialUpdateInputsType0
        from ..models.credential_update_labels_type_0 import CredentialUpdateLabelsType0

        d = dict(src_dict)

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))

        def _parse_inputs(data: object) -> CredentialUpdateInputsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                inputs_type_0 = CredentialUpdateInputsType0.from_dict(data)

                return inputs_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CredentialUpdateInputsType0 | None | Unset, data)

        inputs = _parse_inputs(d.pop("inputs", UNSET))

        def _parse_labels(data: object) -> CredentialUpdateLabelsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                labels_type_0 = CredentialUpdateLabelsType0.from_dict(data)

                return labels_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CredentialUpdateLabelsType0 | None | Unset, data)

        labels = _parse_labels(d.pop("labels", UNSET))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_project_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                project_id_type_0 = UUID(data)

                return project_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        project_id = _parse_project_id(d.pop("project_id", UNSET))

        credential_update = cls(
            description=description,
            enabled=enabled,
            inputs=inputs,
            labels=labels,
            name=name,
            project_id=project_id,
        )

        return credential_update
