from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="GroupDirectoryEntry")


@_attrs_define
class GroupDirectoryEntry:
    """Lightweight group record for directory lookups.

    Attributes:
        id (UUID):
        name (str):
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

        group_directory_entry = cls(
            id=id,
            name=name,
        )

        return group_directory_entry
