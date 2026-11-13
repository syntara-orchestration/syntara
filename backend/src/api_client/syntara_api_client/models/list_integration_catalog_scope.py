from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.integration_scope import IntegrationScope
from ..types import UNSET, Unset

T = TypeVar("T", bound="ListIntegrationCatalogScope")


@_attrs_define
class ListIntegrationCatalogScope:
    """
    Attributes:
        eq (IntegrationScope | None | Unset): Filter by visibility scope
    """

    eq: IntegrationScope | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eq: None | str | Unset
        if isinstance(self.eq, Unset):
            eq = UNSET
        elif isinstance(self.eq, IntegrationScope):
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

        def _parse_eq(data: object) -> IntegrationScope | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                eq_type_0 = IntegrationScope(data)

                return eq_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IntegrationScope | None | Unset, data)

        eq = _parse_eq(d.pop("eq", UNSET))

        list_integration_catalog_scope = cls(
            eq=eq,
        )

        list_integration_catalog_scope.additional_properties = d
        return list_integration_catalog_scope

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
