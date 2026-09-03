from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.identity_provider_read_labels import IdentityProviderReadLabels
    from ..models.oidc_configuration_response import OIDCConfigurationResponse
    from ..models.user_reference import UserReference


T = TypeVar("T", bound="IdentityProviderRead")


@_attrs_define
class IdentityProviderRead:
    """Schema for IdentityProvider response with configuration details (excludes secrets).

    Attributes:
        name (str): Human-readable provider name Example: Authentication Service.
        configuration (OIDCConfigurationResponse): Response schema for OIDC configuration (excludes client_secret).
        id (UUID | Unset): Unique identifier for the resource Example: 550e8400-e29b-41d4-a716-446655440000.
        created_at (datetime.datetime | Unset): Timestamp when resource was created Example: 2025-10-09T12:00:00Z.
        updated_at (datetime.datetime | Unset): Timestamp when resource was last updated Example: 2025-10-09T12:30:00Z.
        labels (IdentityProviderReadLabels | Unset): Key-value pairs for resource labeling and filtering Example:
            {'environment': 'production', 'region': 'us-east-1', 'team': 'platform'}.
        description (None | str | Unset): Detailed description of the resource Example: Handles user authentication and
            authorization workflows.
        created_by (None | Unset | UserReference): User who created the identity provider
        updated_by (None | Unset | UserReference): User who last modified the identity provider
        enabled (bool | Unset): Enable/disable the identity provider Default: True.
    """

    name: str
    configuration: OIDCConfigurationResponse
    id: UUID | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    updated_at: datetime.datetime | Unset = UNSET
    labels: IdentityProviderReadLabels | Unset = UNSET
    description: None | str | Unset = UNSET
    created_by: None | Unset | UserReference = UNSET
    updated_by: None | Unset | UserReference = UNSET
    enabled: bool | Unset = True

    def to_dict(self) -> dict[str, Any]:
        from ..models.user_reference import UserReference

        name = self.name

        configuration = self.configuration.to_dict()

        id: str | Unset = UNSET
        if not isinstance(self.id, Unset):
            id = str(self.id)

        created_at: str | Unset = UNSET
        if not isinstance(self.created_at, Unset):
            created_at = self.created_at.isoformat()

        updated_at: str | Unset = UNSET
        if not isinstance(self.updated_at, Unset):
            updated_at = self.updated_at.isoformat()

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        created_by: dict[str, Any] | None | Unset
        if isinstance(self.created_by, Unset):
            created_by = UNSET
        elif isinstance(self.created_by, UserReference):
            created_by = self.created_by.to_dict()
        else:
            created_by = self.created_by

        updated_by: dict[str, Any] | None | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        elif isinstance(self.updated_by, UserReference):
            updated_by = self.updated_by.to_dict()
        else:
            updated_by = self.updated_by

        enabled = self.enabled

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "configuration": configuration,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if labels is not UNSET:
            field_dict["labels"] = labels
        if description is not UNSET:
            field_dict["description"] = description
        if created_by is not UNSET:
            field_dict["created_by"] = created_by
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by
        if enabled is not UNSET:
            field_dict["enabled"] = enabled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.identity_provider_read_labels import IdentityProviderReadLabels
        from ..models.oidc_configuration_response import OIDCConfigurationResponse
        from ..models.user_reference import UserReference

        d = dict(src_dict)
        name = d.pop("name")

        configuration = OIDCConfigurationResponse.from_dict(d.pop("configuration"))

        _id = d.pop("id", UNSET)
        id: UUID | Unset
        if isinstance(_id, Unset):
            id = UNSET
        else:
            id = UUID(_id)

        _created_at = d.pop("created_at", UNSET)
        created_at: datetime.datetime | Unset
        if isinstance(_created_at, Unset):
            created_at = UNSET
        else:
            created_at = isoparse(_created_at)

        _updated_at = d.pop("updated_at", UNSET)
        updated_at: datetime.datetime | Unset
        if isinstance(_updated_at, Unset):
            updated_at = UNSET
        else:
            updated_at = isoparse(_updated_at)

        _labels = d.pop("labels", UNSET)
        labels: IdentityProviderReadLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = IdentityProviderReadLabels.from_dict(_labels)

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_created_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                created_by_type_0 = UserReference.from_dict(data)

                return created_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        created_by = _parse_created_by(d.pop("created_by", UNSET))

        def _parse_updated_by(data: object) -> None | Unset | UserReference:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                updated_by_type_0 = UserReference.from_dict(data)

                return updated_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserReference, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        enabled = d.pop("enabled", UNSET)

        identity_provider_read = cls(
            name=name,
            configuration=configuration,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            labels=labels,
            description=description,
            created_by=created_by,
            updated_by=updated_by,
            enabled=enabled,
        )

        return identity_provider_read
