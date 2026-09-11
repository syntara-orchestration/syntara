from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="OIDCGroupMappingEntry")


@_attrs_define
class OIDCGroupMappingEntry:
    """API-facing schema for a single IdP-to-Orchestrator group mapping entry.

    Used in API requests/responses. Actual storage is in the
    ``idp_group_mapping_entries`` table.

        Attributes:
            idp_group_value (str): Group value from the IdP token (e.g. GUID or role name)
            mapped_group_id (UUID): ID of the group to map to
    """

    idp_group_value: str
    mapped_group_id: UUID

    def to_dict(self) -> dict[str, Any]:
        idp_group_value = self.idp_group_value

        mapped_group_id = str(self.mapped_group_id)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "idp_group_value": idp_group_value,
                "mapped_group_id": mapped_group_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        idp_group_value = d.pop("idp_group_value")

        mapped_group_id = UUID(d.pop("mapped_group_id"))

        oidc_group_mapping_entry = cls(
            idp_group_value=idp_group_value,
            mapped_group_id=mapped_group_id,
        )

        return oidc_group_mapping_entry
