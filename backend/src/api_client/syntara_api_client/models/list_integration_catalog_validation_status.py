from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.integration_status import IntegrationStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="ListIntegrationCatalogValidationStatus")


@_attrs_define
class ListIntegrationCatalogValidationStatus:
    """
    Attributes:
        eq (IntegrationStatus | None | Unset): Filter by validation status
    """

    eq: IntegrationStatus | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eq: None | str | Unset
        if isinstance(self.eq, Unset):
            eq = UNSET
        elif isinstance(self.eq, IntegrationStatus):
            eq = self.eq.value
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

        def _parse_eq(data: object) -> IntegrationStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                eq_type_0 = IntegrationStatus(data)

                return eq_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IntegrationStatus | None | Unset, data)

        eq = _parse_eq(d.pop("eq", UNSET))

        list_integration_catalog_validation_status = cls(
            eq=eq,
        )

        list_integration_catalog_validation_status.additional_properties = d
        return list_integration_catalog_validation_status

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
