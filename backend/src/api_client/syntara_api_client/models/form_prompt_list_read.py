from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.form_prompt_status import FormPromptStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.user_reference import UserReference


T = TypeVar("T", bound="FormPromptListRead")


@_attrs_define
class FormPromptListRead:
    """User-facing form prompt row for list endpoints (Tasks / Form responses table).

    Attributes:
        id (UUID): Form prompt unique identifier
        created_at (datetime.datetime): When the form prompt was created
        execution_id (UUID): Parent workflow execution ID
        project_id (UUID): Project ID (denormalized from execution)
        prompt_node_id (str): Canvas node ID from the workflow definition
        name (str): Display name for the form prompt
        status (FormPromptStatus): Form prompt status enumeration.
        timeout_at (datetime.datetime | None | Unset): When this prompt expires (null = no timeout)
        responded_at (datetime.datetime | None | Unset): When the response was submitted (null until submitted)
        responded_by (None | Unset | UserReference): User who submitted the response
        workflow_id (None | Unset | UUID): ID of the parent workflow
        workflow_version (int | None | Unset): Integer version number of the workflow version executed
        workflow_name (None | str | Unset): Name of the parent workflow
    """

    id: UUID
    created_at: datetime.datetime
    execution_id: UUID
    project_id: UUID
    prompt_node_id: str
    name: str
    status: FormPromptStatus
    timeout_at: datetime.datetime | None | Unset = UNSET
    responded_at: datetime.datetime | None | Unset = UNSET
    responded_by: None | Unset | UserReference = UNSET
    workflow_id: None | Unset | UUID = UNSET
    workflow_version: int | None | Unset = UNSET
    workflow_name: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.user_reference import UserReference

        id = str(self.id)

        created_at = self.created_at.isoformat()

        execution_id = str(self.execution_id)

        project_id = str(self.project_id)

        prompt_node_id = self.prompt_node_id

        name = self.name

        status = self.status.value

        timeout_at: None | str | Unset
        if isinstance(self.timeout_at, Unset):
            timeout_at = UNSET
        elif isinstance(self.timeout_at, datetime.datetime):
            timeout_at = self.timeout_at.isoformat()
        else:
            timeout_at = self.timeout_at

        responded_at: None | str | Unset
        if isinstance(self.responded_at, Unset):
            responded_at = UNSET
        elif isinstance(self.responded_at, datetime.datetime):
            responded_at = self.responded_at.isoformat()
        else:
            responded_at = self.responded_at

        responded_by: dict[str, Any] | None | Unset
        if isinstance(self.responded_by, Unset):
            responded_by = UNSET
        elif isinstance(self.responded_by, UserReference):
            responded_by = self.responded_by.to_dict()
        else:
            responded_by = self.responded_by

        workflow_id: None | str | Unset
        if isinstance(self.workflow_id, Unset):
            workflow_id = UNSET
        elif isinstance(self.workflow_id, UUID):
            workflow_id = str(self.workflow_id)
        else:
            workflow_id = self.workflow_id

        workflow_version: int | None | Unset
        if isinstance(self.workflow_version, Unset):
            workflow_version = UNSET
        else:
            workflow_version = self.workflow_version

        workflow_name: None | str | Unset
        if isinstance(self.workflow_name, Unset):
            workflow_name = UNSET
        else:
            workflow_name = self.workflow_name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "created_at": created_at,
                "execution_id": execution_id,
                "project_id": project_id,
                "prompt_node_id": prompt_node_id,
                "name": name,
                "status": status,
            }
        )
        if timeout_at is not UNSET:
            field_dict["timeout_at"] = timeout_at
        if responded_at is not UNSET:
            field_dict["responded_at"] = responded_at
        if responded_by is not UNSET:
            field_dict["responded_by"] = responded_by
        if workflow_id is not UNSET:
            field_dict["workflow_id"] = workflow_id
        if workflow_version is not UNSET:
            field_dict["workflow_version"] = workflow_version
        if workflow_name is not UNSET:
            field_dict["workflow_name"] = workflow_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user_reference import UserReference

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        created_at = isoparse(d.pop("created_at"))

        execution_id = UUID(d.pop("execution_id"))

        project_id = UUID(d.pop("project_id"))

        prompt_node_id = d.pop("prompt_node_id")

        name = d.pop("name")

        status = FormPromptStatus(d.pop("status"))

        def _parse_timeout_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                timeout_at_type_0 = isoparse(data)

                return timeout_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        timeout_at = _parse_timeout_at(d.pop("timeout_at", UNSET))

        def _parse_responded_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                responded_at_type_0 = isoparse(data)

                return responded_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        responded_at = _parse_responded_at(d.pop("responded_at", UNSET))

        def _parse_responded_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                responded_by_type_0 = UserReference.from_dict(data)

                return responded_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        responded_by = _parse_responded_by(d.pop("responded_by", UNSET))

        def _parse_workflow_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                workflow_id_type_0 = UUID(data)

                return workflow_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        workflow_id = _parse_workflow_id(d.pop("workflow_id", UNSET))

        def _parse_workflow_version(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        workflow_version = _parse_workflow_version(d.pop("workflow_version", UNSET))

        def _parse_workflow_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        workflow_name = _parse_workflow_name(d.pop("workflow_name", UNSET))

        form_prompt_list_read = cls(
            id=id,
            created_at=created_at,
            execution_id=execution_id,
            project_id=project_id,
            prompt_node_id=prompt_node_id,
            name=name,
            status=status,
            timeout_at=timeout_at,
            responded_at=responded_at,
            responded_by=responded_by,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            workflow_name=workflow_name,
        )

        form_prompt_list_read.additional_properties = d
        return form_prompt_list_read

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
