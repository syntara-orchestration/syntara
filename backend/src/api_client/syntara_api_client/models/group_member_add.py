from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="GroupMemberAdd")


@_attrs_define
class GroupMemberAdd:
    """Schema for adding a member to a group (POST /groups/{id}/members).

    Attributes:
        user_id (UUID): UUID of the user to add to the group
    """

    user_id: UUID

    def to_dict(self) -> dict[str, Any]:
        user_id = str(self.user_id)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "user_id": user_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        user_id = UUID(d.pop("user_id"))

        group_member_add = cls(
            user_id=user_id,
        )

        return group_member_add
