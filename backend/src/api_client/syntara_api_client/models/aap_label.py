from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AAPLabel")


@_attrs_define
class AAPLabel:
    """Ansible Automation Platform label resource.

    Attributes:
        id (int):
        name (str):
        organization (int | None | Unset):
    """

    id: int
    name: str
    organization: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        organization: int | None | Unset
        if isinstance(self.organization, Unset):
            organization = UNSET
        else:
            organization = self.organization

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
            }
        )
        if organization is not UNSET:
            field_dict["organization"] = organization

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        def _parse_organization(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        organization = _parse_organization(d.pop("organization", UNSET))

        aap_label = cls(
            id=id,
            name=name,
            organization=organization,
        )

        return aap_label
