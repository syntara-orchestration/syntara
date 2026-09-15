from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.validation_result import ValidationResult
    from ..models.workflow_read_labels import WorkflowReadLabels


T = TypeVar("T", bound="WorkflowRead")


@_attrs_define
class WorkflowRead:
    """Schema for workflow response (GET /workflows/{id}).

    Includes all fields from the database table model.

        Attributes:
            name (str): Workflow name
            id (UUID):
            current_version (int):
            is_enabled (bool):
            created_by (UUID):
            project_id (UUID):
            created_at (datetime.datetime):
            updated_at (datetime.datetime):
            description (None | str | Unset): Workflow description
            labels (WorkflowReadLabels | Unset): Workflow labels
            is_builtin (bool | Unset):  Default: False.
            has_validation_issues (bool | Unset):  Default: False.
            published_version_id (None | Unset | UUID):
            published_version_number (int | None | Unset):
            validation_result (None | Unset | ValidationResult): Validation findings from the last save operation. Only
                included in create/update responses; use has_validation_issues for the durable indicator.
    """

    name: str
    id: UUID
    current_version: int
    is_enabled: bool
    created_by: UUID
    project_id: UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    description: None | str | Unset = UNSET
    labels: WorkflowReadLabels | Unset = UNSET
    is_builtin: bool | Unset = False
    has_validation_issues: bool | Unset = False
    published_version_id: None | Unset | UUID = UNSET
    published_version_number: int | None | Unset = UNSET
    validation_result: None | Unset | ValidationResult = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.validation_result import ValidationResult

        name = self.name

        id = str(self.id)

        current_version = self.current_version

        is_enabled = self.is_enabled

        created_by = str(self.created_by)

        project_id = str(self.project_id)

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        is_builtin = self.is_builtin

        has_validation_issues = self.has_validation_issues

        published_version_id: None | str | Unset
        if isinstance(self.published_version_id, Unset):
            published_version_id = UNSET
        elif isinstance(self.published_version_id, UUID):
            published_version_id = str(self.published_version_id)
        else:
            published_version_id = self.published_version_id

        published_version_number: int | None | Unset
        if isinstance(self.published_version_number, Unset):
            published_version_number = UNSET
        else:
            published_version_number = self.published_version_number

        validation_result: dict[str, Any] | None | Unset
        if isinstance(self.validation_result, Unset):
            validation_result = UNSET
        elif isinstance(self.validation_result, ValidationResult):
            validation_result = self.validation_result.to_dict()
        else:
            validation_result = self.validation_result

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "id": id,
                "current_version": current_version,
                "is_enabled": is_enabled,
                "created_by": created_by,
                "project_id": project_id,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if labels is not UNSET:
            field_dict["labels"] = labels
        if is_builtin is not UNSET:
            field_dict["is_builtin"] = is_builtin
        if has_validation_issues is not UNSET:
            field_dict["has_validation_issues"] = has_validation_issues
        if published_version_id is not UNSET:
            field_dict["published_version_id"] = published_version_id
        if published_version_number is not UNSET:
            field_dict["published_version_number"] = published_version_number
        if validation_result is not UNSET:
            field_dict["validation_result"] = validation_result

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validation_result import ValidationResult
        from ..models.workflow_read_labels import WorkflowReadLabels

        d = dict(src_dict)
        name = d.pop("name")

        id = UUID(d.pop("id"))

        current_version = d.pop("current_version")

        is_enabled = d.pop("is_enabled")

        created_by = UUID(d.pop("created_by"))

        project_id = UUID(d.pop("project_id"))

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        _labels = d.pop("labels", UNSET)
        labels: WorkflowReadLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = WorkflowReadLabels.from_dict(_labels)

        is_builtin = d.pop("is_builtin", UNSET)

        has_validation_issues = d.pop("has_validation_issues", UNSET)

        def _parse_published_version_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                published_version_id_type_0 = UUID(data)

                return published_version_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        published_version_id = _parse_published_version_id(d.pop("published_version_id", UNSET))

        def _parse_published_version_number(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        published_version_number = _parse_published_version_number(d.pop("published_version_number", UNSET))

        def _parse_validation_result(data: object) -> None | Unset | ValidationResult:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                validation_result_type_0 = ValidationResult.from_dict(data)

                return validation_result_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | ValidationResult, data)

        validation_result = _parse_validation_result(d.pop("validation_result", UNSET))

        workflow_read = cls(
            name=name,
            id=id,
            current_version=current_version,
            is_enabled=is_enabled,
            created_by=created_by,
            project_id=project_id,
            created_at=created_at,
            updated_at=updated_at,
            description=description,
            labels=labels,
            is_builtin=is_builtin,
            has_validation_issues=has_validation_issues,
            published_version_id=published_version_id,
            published_version_number=published_version_number,
            validation_result=validation_result,
        )

        workflow_read.additional_properties = d
        return workflow_read

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
