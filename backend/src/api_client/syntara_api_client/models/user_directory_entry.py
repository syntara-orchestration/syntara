from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="UserDirectoryEntry")


@_attrs_define
class UserDirectoryEntry:
    """Lightweight user record for directory lookups.

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

        user_directory_entry = cls(
            id=id,
            username=username,
        )

        return user_directory_entry
