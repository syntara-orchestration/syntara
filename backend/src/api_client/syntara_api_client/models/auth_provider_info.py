from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AuthProviderInfo")


@_attrs_define
class AuthProviderInfo:
    """Public identity provider info for the login page.

    Attributes:
        id (str): Provider UUID
        name (str): Provider display name
        provider_type (str): Provider type (e.g. oidc)
        provider_template (None | str | Unset): Provider template (e.g. aap)
    """

    id: str
    name: str
    provider_type: str
    provider_template: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        provider_type = self.provider_type

        provider_template: None | str | Unset
        if isinstance(self.provider_template, Unset):
            provider_template = UNSET
        else:
            provider_template = self.provider_template

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
                "provider_type": provider_type,
            }
        )
        if provider_template is not UNSET:
            field_dict["provider_template"] = provider_template

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        provider_type = d.pop("provider_type")

        def _parse_provider_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_template = _parse_provider_template(d.pop("provider_template", UNSET))

        auth_provider_info = cls(
            id=id,
            name=name,
            provider_type=provider_type,
            provider_template=provider_template,
        )

        return auth_provider_info
