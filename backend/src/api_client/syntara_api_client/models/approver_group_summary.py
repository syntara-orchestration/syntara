from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="ApproverGroupSummary")


@_attrs_define
class ApproverGroupSummary:
    """Summary of a group whose members are authorized to approve a request.

    Represents a group of users who can collectively approve a request.
    Used in API responses to show which groups have approval authority.

        Attributes:
            id (UUID): Group's unique identifier
            name (str): Group's name
    """

    id: UUID
    name: str

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        name = self.name

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        name = d.pop("name")

        approver_group_summary = cls(
            id=id,
            name=name,
        )

        return approver_group_summary
