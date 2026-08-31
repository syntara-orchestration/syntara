from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.service_account_status import ServiceAccountStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.service_account_read_labels import ServiceAccountReadLabels
    from ..models.user_reference import UserReference


T = TypeVar("T", bound="ServiceAccountRead")


@_attrs_define
class ServiceAccountRead:
    """Schema for service account responses.

    Attributes:
        id (UUID):
        name (str):
        status (ServiceAccountStatus): Operational status of a service account.
        project_id (UUID):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        description (None | str | Unset):
        project_name (None | str | Unset):
        is_project_deleted (bool | Unset):  Default: False.
        last_authenticated_at (datetime.datetime | None | Unset):
        created_by (None | Unset | UserReference): User who created the service account
        updated_by (None | Unset | UserReference): User who last modified the service account
        labels (ServiceAccountReadLabels | Unset):
    """

    id: UUID
    name: str
    status: ServiceAccountStatus
    project_id: UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    description: None | str | Unset = UNSET
    project_name: None | str | Unset = UNSET
    is_project_deleted: bool | Unset = False
    last_authenticated_at: datetime.datetime | None | Unset = UNSET
    created_by: None | Unset | UserReference = UNSET
    updated_by: None | Unset | UserReference = UNSET
    labels: ServiceAccountReadLabels | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.user_reference import UserReference

        id = str(self.id)

        name = self.name

        status = self.status.value

        project_id = str(self.project_id)

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        project_name: None | str | Unset
        if isinstance(self.project_name, Unset):
            project_name = UNSET
        else:
            project_name = self.project_name

        is_project_deleted = self.is_project_deleted

        last_authenticated_at: None | str | Unset
        if isinstance(self.last_authenticated_at, Unset):
            last_authenticated_at = UNSET
        elif isinstance(self.last_authenticated_at, datetime.datetime):
            last_authenticated_at = self.last_authenticated_at.isoformat()
        else:
            last_authenticated_at = self.last_authenticated_at

        created_by: dict[str, Any] | None | Unset
        if isinstance(self.created_by, Unset):
            created_by = UNSET
        elif isinstance(self.created_by, UserReference):
            created_by = self.created_by.to_dict()
        else:
            created_by = self.created_by

        updated_by: dict[str, Any] | None | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        elif isinstance(self.updated_by, UserReference):
            updated_by = self.updated_by.to_dict()
        else:
            updated_by = self.updated_by

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "status": status,
                "project_id": project_id,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if project_name is not UNSET:
            field_dict["project_name"] = project_name
        if is_project_deleted is not UNSET:
            field_dict["is_project_deleted"] = is_project_deleted
        if last_authenticated_at is not UNSET:
            field_dict["last_authenticated_at"] = last_authenticated_at
        if created_by is not UNSET:
            field_dict["created_by"] = created_by
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by
        if labels is not UNSET:
            field_dict["labels"] = labels

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.service_account_read_labels import ServiceAccountReadLabels
        from ..models.user_reference import UserReference

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        name = d.pop("name")

        status = ServiceAccountStatus(d.pop("status"))

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

        def _parse_project_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        project_name = _parse_project_name(d.pop("project_name", UNSET))

        is_project_deleted = d.pop("is_project_deleted", UNSET)

        def _parse_last_authenticated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_authenticated_at_type_0 = isoparse(data)

                return last_authenticated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_authenticated_at = _parse_last_authenticated_at(d.pop("last_authenticated_at", UNSET))

        def _parse_created_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                created_by_type_0 = UserReference.from_dict(data)

                return created_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        created_by = _parse_created_by(d.pop("created_by", UNSET))

        def _parse_updated_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                updated_by_type_0 = UserReference.from_dict(data)

                return updated_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        _labels = d.pop("labels", UNSET)
        labels: ServiceAccountReadLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = ServiceAccountReadLabels.from_dict(_labels)

        service_account_read = cls(
            id=id,
            name=name,
            status=status,
            project_id=project_id,
            created_at=created_at,
            updated_at=updated_at,
            description=description,
            project_name=project_name,
            is_project_deleted=is_project_deleted,
            last_authenticated_at=last_authenticated_at,
            created_by=created_by,
            updated_by=updated_by,
            labels=labels,
        )

        service_account_read.additional_properties = d
        return service_account_read

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
