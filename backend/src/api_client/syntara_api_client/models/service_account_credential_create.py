from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.service_account_credential_type import ServiceAccountCredentialType
from ..types import UNSET, Unset

T = TypeVar("T", bound="ServiceAccountCredentialCreate")


@_attrs_define
class ServiceAccountCredentialCreate:
    """Schema for creating a new service account credential.

    Attributes:
        credential_type (ServiceAccountCredentialType): Type of credential issued for a service account.
        expires_at (datetime.datetime | None | Unset): Optional expiry timestamp (must include timezone). If omitted,
            auto-set from the configured maximum credential lifetime. Rejected if it exceeds the configured limit.
        grace_period_seconds (int | Unset): Duration (seconds) old secret remains valid after rotation Default: 3600.
    """

    credential_type: ServiceAccountCredentialType
    expires_at: datetime.datetime | None | Unset = UNSET
    grace_period_seconds: int | Unset = 3600
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        credential_type = self.credential_type.value

        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        elif isinstance(self.expires_at, datetime.datetime):
            expires_at = self.expires_at.isoformat()
        else:
            expires_at = self.expires_at

        grace_period_seconds = self.grace_period_seconds

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "credential_type": credential_type,
            }
        )
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at
        if grace_period_seconds is not UNSET:
            field_dict["grace_period_seconds"] = grace_period_seconds

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        credential_type = ServiceAccountCredentialType(d.pop("credential_type"))

        def _parse_expires_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                expires_at_type_0 = isoparse(data)

                return expires_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))

        grace_period_seconds = d.pop("grace_period_seconds", UNSET)

        service_account_credential_create = cls(
            credential_type=credential_type,
            expires_at=expires_at,
            grace_period_seconds=grace_period_seconds,
        )

        service_account_credential_create.additional_properties = d
        return service_account_credential_create

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
