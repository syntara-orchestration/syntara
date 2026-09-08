from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.workflow_version_read_status import WorkflowVersionReadStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_version_read_workflow_definition import WorkflowVersionReadWorkflowDefinition


T = TypeVar("T", bound="WorkflowVersionRead")


@_attrs_define
class WorkflowVersionRead:
    """Schema for workflow version response (GET /workflows/{id}/versions/{version}).

    Attributes:
        id (UUID):
        workflow_id (UUID):
        version (int):
        schema_version (str):
        workflow_definition (WorkflowVersionReadWorkflowDefinition):
        created_by (UUID):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        change_description (None | str | Unset):
        status (WorkflowVersionReadStatus | Unset):  Default: WorkflowVersionReadStatus.DRAFT.
        last_published_at (datetime.datetime | None | Unset):
        last_unpublished_at (datetime.datetime | None | Unset):
        name (None | str | Unset):
        created_by_username (None | str | Unset):
    """

    id: UUID
    workflow_id: UUID
    version: int
    schema_version: str
    workflow_definition: WorkflowVersionReadWorkflowDefinition
    created_by: UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    change_description: None | str | Unset = UNSET
    status: WorkflowVersionReadStatus | Unset = WorkflowVersionReadStatus.DRAFT
    last_published_at: datetime.datetime | None | Unset = UNSET
    last_unpublished_at: datetime.datetime | None | Unset = UNSET
    name: None | str | Unset = UNSET
    created_by_username: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        workflow_id = str(self.workflow_id)

        version = self.version

        schema_version = self.schema_version

        workflow_definition = self.workflow_definition.to_dict()

        created_by = str(self.created_by)

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        change_description: None | str | Unset
        if isinstance(self.change_description, Unset):
            change_description = UNSET
        else:
            change_description = self.change_description

        status: str | Unset = UNSET
        if not isinstance(self.status, Unset):
            status = self.status.value

        last_published_at: None | str | Unset
        if isinstance(self.last_published_at, Unset):
            last_published_at = UNSET
        elif isinstance(self.last_published_at, datetime.datetime):
            last_published_at = self.last_published_at.isoformat()
        else:
            last_published_at = self.last_published_at

        last_unpublished_at: None | str | Unset
        if isinstance(self.last_unpublished_at, Unset):
            last_unpublished_at = UNSET
        elif isinstance(self.last_unpublished_at, datetime.datetime):
            last_unpublished_at = self.last_unpublished_at.isoformat()
        else:
            last_unpublished_at = self.last_unpublished_at

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        created_by_username: None | str | Unset
        if isinstance(self.created_by_username, Unset):
            created_by_username = UNSET
        else:
            created_by_username = self.created_by_username

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workflow_id": workflow_id,
                "version": version,
                "schema_version": schema_version,
                "workflow_definition": workflow_definition,
                "created_by": created_by,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if change_description is not UNSET:
            field_dict["change_description"] = change_description
        if status is not UNSET:
            field_dict["status"] = status
        if last_published_at is not UNSET:
            field_dict["last_published_at"] = last_published_at
        if last_unpublished_at is not UNSET:
            field_dict["last_unpublished_at"] = last_unpublished_at
        if name is not UNSET:
            field_dict["name"] = name
        if created_by_username is not UNSET:
            field_dict["created_by_username"] = created_by_username

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_version_read_workflow_definition import WorkflowVersionReadWorkflowDefinition

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        workflow_id = UUID(d.pop("workflow_id"))

        version = d.pop("version")

        schema_version = d.pop("schema_version")

        workflow_definition = WorkflowVersionReadWorkflowDefinition.from_dict(d.pop("workflow_definition"))

        created_by = UUID(d.pop("created_by"))

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_change_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        change_description = _parse_change_description(d.pop("change_description", UNSET))

        _status = d.pop("status", UNSET)
        status: WorkflowVersionReadStatus | Unset
        if isinstance(_status, Unset):
            status = UNSET
        else:
            status = WorkflowVersionReadStatus(_status)

        def _parse_last_published_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_published_at_type_0 = isoparse(data)

                return last_published_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_published_at = _parse_last_published_at(d.pop("last_published_at", UNSET))

        def _parse_last_unpublished_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_unpublished_at_type_0 = isoparse(data)

                return last_unpublished_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_unpublished_at = _parse_last_unpublished_at(d.pop("last_unpublished_at", UNSET))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_created_by_username(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        created_by_username = _parse_created_by_username(d.pop("created_by_username", UNSET))

        workflow_version_read = cls(
            id=id,
            workflow_id=workflow_id,
            version=version,
            schema_version=schema_version,
            workflow_definition=workflow_definition,
            created_by=created_by,
            created_at=created_at,
            updated_at=updated_at,
            change_description=change_description,
            status=status,
            last_published_at=last_published_at,
            last_unpublished_at=last_unpublished_at,
            name=name,
            created_by_username=created_by_username,
        )

        workflow_version_read.additional_properties = d
        return workflow_version_read

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
