from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="GroupMemberAddResponse")


@_attrs_define
class GroupMemberAddResponse:
    """Response schema for adding a member to a group.

    Attributes:
        message (str | Unset): Confirmation message Default: 'Member added successfully'.
    """

    message: str | Unset = "Member added successfully"

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if message is not UNSET:
            field_dict["message"] = message

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message", UNSET)

        group_member_add_response = cls(
            message=message,
        )

        return group_member_add_response
