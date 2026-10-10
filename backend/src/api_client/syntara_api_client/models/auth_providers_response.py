from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.auth_provider_info import AuthProviderInfo


T = TypeVar("T", bound="AuthProvidersResponse")


@_attrs_define
class AuthProvidersResponse:
    """Response for the public providers listing endpoint.

    Attributes:
        resources (list[AuthProviderInfo] | Unset): Enabled identity providers
    """

    resources: list[AuthProviderInfo] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        resources: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.resources, Unset):
            resources = []
            for resources_item_data in self.resources:
                resources_item = resources_item_data.to_dict()
                resources.append(resources_item)

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if resources is not UNSET:
            field_dict["resources"] = resources

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.auth_provider_info import AuthProviderInfo

        d = dict(src_dict)
        _resources = d.pop("resources", UNSET)
        resources: list[AuthProviderInfo] | Unset = UNSET
        if _resources is not UNSET:
            resources = []
            for resources_item_data in _resources:
                resources_item = AuthProviderInfo.from_dict(resources_item_data)

                resources.append(resources_item)

        auth_providers_response = cls(
            resources=resources,
        )

        return auth_providers_response
