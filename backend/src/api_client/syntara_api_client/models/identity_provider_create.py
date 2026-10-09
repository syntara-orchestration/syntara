from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.oidc_configuration import OIDCConfiguration


T = TypeVar("T", bound="IdentityProviderCreate")


@_attrs_define
class IdentityProviderCreate:
    """Schema for creating a new identity provider.

    Attributes:
        name (str): Human-readable name for the provider
        configuration (OIDCConfiguration): Configuration for OIDC (OpenID Connect) providers.
        description (None | str | Unset): Detailed description of the provider
    """

    name: str
    configuration: OIDCConfiguration
    description: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        configuration = self.configuration.to_dict()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "configuration": configuration,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.oidc_configuration import OIDCConfiguration

        d = dict(src_dict)
        name = d.pop("name")

        configuration = OIDCConfiguration.from_dict(d.pop("configuration"))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        identity_provider_create = cls(
            name=name,
            configuration=configuration,
            description=description,
        )

        return identity_provider_create
