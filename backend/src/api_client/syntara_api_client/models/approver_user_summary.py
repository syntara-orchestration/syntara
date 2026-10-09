from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="ApproverUserSummary")


@_attrs_define
class ApproverUserSummary:
    """Summary of a user authorized to approve a request.

    Similar to UserReference but represents an approver rather than a decider.
    Used in API responses to show who can approve a request.

        Attributes:
            id (UUID): User's unique identifier
            username (str): User's username
    """

    id: UUID
    username: str

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        username = self.username

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "username": username,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        username = d.pop("username")

        approver_user_summary = cls(
            id=id,
            username=username,
        )

        return approver_user_summary
