from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RoleAssignmentCreate")


@_attrs_define
class RoleAssignmentCreate:
    """Request body for creating a role assignment.

    Exactly one of ``principal_id`` or ``group_id`` must be provided.
    At most one of ``project_id`` or ``project_pattern`` may be provided.

        Attributes:
            role_name (str):
            principal_id (None | Unset | UUID):
            group_id (None | Unset | UUID):
            project_id (None | Unset | UUID):
            project_pattern (None | str | Unset): Project-name pattern using '*' as a wildcard (for example 'pay*'). The
                assignment then applies to every project whose current name matches. Only custom, deny-only, project-scope roles
                can be assigned with a pattern. Mutually exclusive with project_id.
    """

    role_name: str
    principal_id: None | Unset | UUID = UNSET
    group_id: None | Unset | UUID = UNSET
    project_id: None | Unset | UUID = UNSET
    project_pattern: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        role_name = self.role_name

        principal_id: None | str | Unset
        if isinstance(self.principal_id, Unset):
            principal_id = UNSET
        elif isinstance(self.principal_id, UUID):
            principal_id = str(self.principal_id)
        else:
            principal_id = self.principal_id

        group_id: None | str | Unset
        if isinstance(self.group_id, Unset):
            group_id = UNSET
        elif isinstance(self.group_id, UUID):
            group_id = str(self.group_id)
        else:
            group_id = self.group_id

        project_id: None | str | Unset
        if isinstance(self.project_id, Unset):
            project_id = UNSET
        elif isinstance(self.project_id, UUID):
            project_id = str(self.project_id)
        else:
            project_id = self.project_id

        project_pattern: None | str | Unset
        if isinstance(self.project_pattern, Unset):
            project_pattern = UNSET
        else:
            project_pattern = self.project_pattern

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "role_name": role_name,
            }
        )
        if principal_id is not UNSET:
            field_dict["principal_id"] = principal_id
        if group_id is not UNSET:
            field_dict["group_id"] = group_id
        if project_id is not UNSET:
            field_dict["project_id"] = project_id
        if project_pattern is not UNSET:
            field_dict["project_pattern"] = project_pattern

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        role_name = d.pop("role_name")

        def _parse_principal_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                principal_id_type_0 = UUID(data)

                return principal_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        principal_id = _parse_principal_id(d.pop("principal_id", UNSET))

        def _parse_group_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                group_id_type_0 = UUID(data)

                return group_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        group_id = _parse_group_id(d.pop("group_id", UNSET))

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

        def _parse_project_pattern(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        project_pattern = _parse_project_pattern(d.pop("project_pattern", UNSET))

        role_assignment_create = cls(
            role_name=role_name,
            principal_id=principal_id,
            group_id=group_id,
            project_id=project_id,
            project_pattern=project_pattern,
        )

        role_assignment_create.additional_properties = d
        return role_assignment_create

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
