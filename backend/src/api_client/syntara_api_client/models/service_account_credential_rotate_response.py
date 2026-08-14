from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.service_account_credential_status import ServiceAccountCredentialStatus
from ..models.service_account_credential_type import ServiceAccountCredentialType
from ..types import UNSET, Unset

T = TypeVar("T", bound="ServiceAccountCredentialRotateResponse")


@_attrs_define
class ServiceAccountCredentialRotateResponse:
    """Schema for the rotate response — same shape as create response.

    Attributes:
        id (UUID):
        service_account_id (UUID):
        credential_type (ServiceAccountCredentialType): Type of credential issued for a service account.
        identifier (str):
        status (ServiceAccountCredentialStatus): Operational status of a service account credential.
        grace_period_seconds (int):
        created_by (UUID):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        expires_at (datetime.datetime | None | Unset):
        last_used_at (datetime.datetime | None | Unset):
        old_secret_valid_until (datetime.datetime | None | Unset):
        updated_by (None | Unset | UUID):
        client_secret (None | str | Unset): Plaintext client secret (shown only once)
    """

    id: UUID
    service_account_id: UUID
    credential_type: ServiceAccountCredentialType
    identifier: str
    status: ServiceAccountCredentialStatus
    grace_period_seconds: int
    created_by: UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    expires_at: datetime.datetime | None | Unset = UNSET
    last_used_at: datetime.datetime | None | Unset = UNSET
    old_secret_valid_until: datetime.datetime | None | Unset = UNSET
    updated_by: None | Unset | UUID = UNSET
    client_secret: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        service_account_id = str(self.service_account_id)

        credential_type = self.credential_type.value

        identifier = self.identifier

        status = self.status.value

        grace_period_seconds = self.grace_period_seconds

        created_by = str(self.created_by)

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        elif isinstance(self.expires_at, datetime.datetime):
            expires_at = self.expires_at.isoformat()
        else:
            expires_at = self.expires_at

        last_used_at: None | str | Unset
        if isinstance(self.last_used_at, Unset):
            last_used_at = UNSET
        elif isinstance(self.last_used_at, datetime.datetime):
            last_used_at = self.last_used_at.isoformat()
        else:
            last_used_at = self.last_used_at

        old_secret_valid_until: None | str | Unset
        if isinstance(self.old_secret_valid_until, Unset):
            old_secret_valid_until = UNSET
        elif isinstance(self.old_secret_valid_until, datetime.datetime):
            old_secret_valid_until = self.old_secret_valid_until.isoformat()
        else:
            old_secret_valid_until = self.old_secret_valid_until

        updated_by: None | str | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        elif isinstance(self.updated_by, UUID):
            updated_by = str(self.updated_by)
        else:
            updated_by = self.updated_by

        client_secret: None | str | Unset
        if isinstance(self.client_secret, Unset):
            client_secret = UNSET
        else:
            client_secret = self.client_secret

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "service_account_id": service_account_id,
                "credential_type": credential_type,
                "identifier": identifier,
                "status": status,
                "grace_period_seconds": grace_period_seconds,
                "created_by": created_by,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at
        if last_used_at is not UNSET:
            field_dict["last_used_at"] = last_used_at
        if old_secret_valid_until is not UNSET:
            field_dict["old_secret_valid_until"] = old_secret_valid_until
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by
        if client_secret is not UNSET:
            field_dict["client_secret"] = client_secret

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        service_account_id = UUID(d.pop("service_account_id"))

        credential_type = ServiceAccountCredentialType(d.pop("credential_type"))

        identifier = d.pop("identifier")

        status = ServiceAccountCredentialStatus(d.pop("status"))

        grace_period_seconds = d.pop("grace_period_seconds")

        created_by = UUID(d.pop("created_by"))

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

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

        def _parse_last_used_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_used_at_type_0 = isoparse(data)

                return last_used_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_used_at = _parse_last_used_at(d.pop("last_used_at", UNSET))

        def _parse_old_secret_valid_until(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                old_secret_valid_until_type_0 = isoparse(data)

                return old_secret_valid_until_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        old_secret_valid_until = _parse_old_secret_valid_until(d.pop("old_secret_valid_until", UNSET))

        def _parse_updated_by(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_by_type_0 = UUID(data)

                return updated_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        def _parse_client_secret(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        client_secret = _parse_client_secret(d.pop("client_secret", UNSET))

        service_account_credential_rotate_response = cls(
            id=id,
            service_account_id=service_account_id,
            credential_type=credential_type,
            identifier=identifier,
            status=status,
            grace_period_seconds=grace_period_seconds,
            created_by=created_by,
            created_at=created_at,
            updated_at=updated_at,
            expires_at=expires_at,
            last_used_at=last_used_at,
            old_secret_valid_until=old_secret_valid_until,
            updated_by=updated_by,
            client_secret=client_secret,
        )

        service_account_credential_rotate_response.additional_properties = d
        return service_account_credential_rotate_response

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
