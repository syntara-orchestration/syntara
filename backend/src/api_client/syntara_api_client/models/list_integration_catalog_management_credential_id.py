from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListIntegrationCatalogManagementCredentialId")


@_attrs_define
class ListIntegrationCatalogManagementCredentialId:
    """
    Attributes:
        eq (None | Unset | UUID): Filter by management credential ID
    """

    eq: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eq: None | str | Unset
        if isinstance(self.eq, Unset):
            eq = UNSET
        elif isinstance(self.eq, UUID):
            eq = str(self.eq)
        else:
            eq = self.eq

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if eq is not UNSET:
            field_dict["eq"] = eq

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_eq(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                eq_type_0 = UUID(data)

                return eq_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        eq = _parse_eq(d.pop("eq", UNSET))

        list_integration_catalog_management_credential_id = cls(
            eq=eq,
        )

        list_integration_catalog_management_credential_id.additional_properties = d
        return list_integration_catalog_management_credential_id

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
