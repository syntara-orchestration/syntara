from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="WhoCanUser")


@_attrs_define
class WhoCanUser:
    """A user who can perform the requested action.

    Attributes:
        id (UUID):
        username (str):
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

        who_can_user = cls(
            id=id,
            username=username,
        )

        return who_can_user
