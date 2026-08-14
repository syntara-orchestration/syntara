from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.oidc_configuration_update import OIDCConfigurationUpdate


T = TypeVar("T", bound="IdentityProviderUpdate")


@_attrs_define
class IdentityProviderUpdate:
    """Schema for partially updating an identity provider.

    Attributes:
        name (None | str | Unset): Human-readable name for the provider
        description (None | str | Unset): Detailed description of the provider
        configuration (None | OIDCConfigurationUpdate | Unset): Provider-specific configuration (client_secret optional
            — preserves existing if omitted)
        enabled (bool | None | Unset): Enable/disable the provider
    """

    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    configuration: None | OIDCConfigurationUpdate | Unset = UNSET
    enabled: bool | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.oidc_configuration_update import OIDCConfigurationUpdate

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        configuration: dict[str, Any] | None | Unset
        if isinstance(self.configuration, Unset):
            configuration = UNSET
        elif isinstance(self.configuration, OIDCConfigurationUpdate):
            configuration = self.configuration.to_dict()
        else:
            configuration = self.configuration

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if description is not UNSET:
            field_dict["description"] = description
        if configuration is not UNSET:
            field_dict["configuration"] = configuration
        if enabled is not UNSET:
            field_dict["enabled"] = enabled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.oidc_configuration_update import OIDCConfigurationUpdate

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_configuration(data: object) -> None | OIDCConfigurationUpdate | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                configuration_type_0 = OIDCConfigurationUpdate.from_dict(data)

                return configuration_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OIDCConfigurationUpdate | Unset, data)

        configuration = _parse_configuration(d.pop("configuration", UNSET))

        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))

        identity_provider_update = cls(
            name=name,
            description=description,
            configuration=configuration,
            enabled=enabled,
        )

        return identity_provider_update
