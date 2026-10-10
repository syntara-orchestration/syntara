from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.model_capability_profile import ModelCapabilityProfile


T = TypeVar("T", bound="LLMModelRead")


@_attrs_define
class LLMModelRead:
    """Schema for LLM model API responses.

    Attributes:
        id (UUID):
        integration_id (UUID):
        model_id (str):
        name (str):
        description (None | str | Unset):
        enabled (bool | Unset):  Default: True.
        is_default (bool | Unset):  Default: False.
        last_refreshed_at (datetime.datetime | None | Unset):
        profile (ModelCapabilityProfile | None | Unset): Model capability profile
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
    """

    id: UUID
    integration_id: UUID
    model_id: str
    name: str
    description: None | str | Unset = UNSET
    enabled: bool | Unset = True
    is_default: bool | Unset = False
    last_refreshed_at: datetime.datetime | None | Unset = UNSET
    profile: ModelCapabilityProfile | None | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.model_capability_profile import ModelCapabilityProfile

        id = str(self.id)

        integration_id = str(self.integration_id)

        model_id = self.model_id

        name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        enabled = self.enabled

        is_default = self.is_default

        last_refreshed_at: None | str | Unset
        if isinstance(self.last_refreshed_at, Unset):
            last_refreshed_at = UNSET
        elif isinstance(self.last_refreshed_at, datetime.datetime):
            last_refreshed_at = self.last_refreshed_at.isoformat()
        else:
            last_refreshed_at = self.last_refreshed_at

        profile: dict[str, Any] | None | Unset
        if isinstance(self.profile, Unset):
            profile = UNSET
        elif isinstance(self.profile, ModelCapabilityProfile):
            profile = self.profile.to_dict()
        else:
            profile = self.profile

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "integration_id": integration_id,
                "model_id": model_id,
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if is_default is not UNSET:
            field_dict["is_default"] = is_default
        if last_refreshed_at is not UNSET:
            field_dict["last_refreshed_at"] = last_refreshed_at
        if profile is not UNSET:
            field_dict["profile"] = profile
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.model_capability_profile import ModelCapabilityProfile

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        integration_id = UUID(d.pop("integration_id"))

        model_id = d.pop("model_id")

        name = d.pop("name")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        enabled = d.pop("enabled", UNSET)

        is_default = d.pop("is_default", UNSET)

        def _parse_last_refreshed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_refreshed_at_type_0 = isoparse(data)

                return last_refreshed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_refreshed_at = _parse_last_refreshed_at(d.pop("last_refreshed_at", UNSET))

        def _parse_profile(data: object) -> ModelCapabilityProfile | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                profile_type_0 = ModelCapabilityProfile.from_dict(data)

                return profile_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ModelCapabilityProfile | None | Unset, data)

        profile = _parse_profile(d.pop("profile", UNSET))

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        llm_model_read = cls(
            id=id,
            integration_id=integration_id,
            model_id=model_id,
            name=name,
            description=description,
            enabled=enabled,
            is_default=is_default,
            last_refreshed_at=last_refreshed_at,
            profile=profile,
            created_at=created_at,
            updated_at=updated_at,
        )

        return llm_model_read
