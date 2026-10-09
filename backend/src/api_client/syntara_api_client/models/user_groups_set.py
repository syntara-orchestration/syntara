from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="UserGroupsSet")


@_attrs_define
class UserGroupsSet:
    """Schema for declaratively setting a user's group memberships (PUT /users/{id}/groups).

    The provided list replaces all current memberships. An empty list removes
    the user from all groups.

        Attributes:
            group_ids (list[UUID] | Unset): Complete list of group IDs the user should belong to
    """

    group_ids: list[UUID] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        group_ids: list[str] | Unset = UNSET
        if not isinstance(self.group_ids, Unset):
            group_ids = []
            for group_ids_item_data in self.group_ids:
                group_ids_item = str(group_ids_item_data)
                group_ids.append(group_ids_item)

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if group_ids is not UNSET:
            field_dict["group_ids"] = group_ids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        _group_ids = d.pop("group_ids", UNSET)
        group_ids: list[UUID] | Unset = UNSET
        if _group_ids is not UNSET:
            group_ids = []
            for group_ids_item_data in _group_ids:
                group_ids_item = UUID(group_ids_item_data)

                group_ids.append(group_ids_item)

        user_groups_set = cls(
            group_ids=group_ids,
        )

        return user_groups_set
