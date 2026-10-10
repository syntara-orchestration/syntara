from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="AAPInstanceGroup")


@_attrs_define
class AAPInstanceGroup:
    """Ansible Automation Platform instance group resource.

    Attributes:
        id (int):
        name (str):
    """

    id: int
    name: str

    def to_dict(self) -> dict[str, Any]:
        id = self.id

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
        id = d.pop("id")

        name = d.pop("name")

        aap_instance_group = cls(
            id=id,
            name=name,
        )

        return aap_instance_group
