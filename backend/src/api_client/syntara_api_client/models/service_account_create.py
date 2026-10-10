from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ServiceAccountCreate")


@_attrs_define
class ServiceAccountCreate:
    """Schema for creating a new service account.

    Attributes:
        name (str): Human-readable name for the service account
        project_id (UUID): Project to create the service account in
        description (None | str | Unset): Optional description of the service account's purpose
    """

    name: str
    project_id: UUID
    description: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        project_id = str(self.project_id)

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "project_id": project_id,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        project_id = UUID(d.pop("project_id"))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        service_account_create = cls(
            name=name,
            project_id=project_id,
            description=description,
        )

        return service_account_create
