from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="UserIdentityRead")


@_attrs_define
class UserIdentityRead:
    """Schema for user identity response.

    Attributes:
        id (UUID):
        user_id (UUID):
        identity_provider_id (UUID):
        issuer (str):
        subject (str):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        last_used_at (datetime.datetime | None | Unset):
        provider_name (str | Unset):  Default: ''.
    """

    id: UUID
    user_id: UUID
    identity_provider_id: UUID
    issuer: str
    subject: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    last_used_at: datetime.datetime | None | Unset = UNSET
    provider_name: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        user_id = str(self.user_id)

        identity_provider_id = str(self.identity_provider_id)

        issuer = self.issuer

        subject = self.subject

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        last_used_at: None | str | Unset
        if isinstance(self.last_used_at, Unset):
            last_used_at = UNSET
        elif isinstance(self.last_used_at, datetime.datetime):
            last_used_at = self.last_used_at.isoformat()
        else:
            last_used_at = self.last_used_at

        provider_name = self.provider_name

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "user_id": user_id,
                "identity_provider_id": identity_provider_id,
                "issuer": issuer,
                "subject": subject,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if last_used_at is not UNSET:
            field_dict["last_used_at"] = last_used_at
        if provider_name is not UNSET:
            field_dict["provider_name"] = provider_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        user_id = UUID(d.pop("user_id"))

        identity_provider_id = UUID(d.pop("identity_provider_id"))

        issuer = d.pop("issuer")

        subject = d.pop("subject")

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

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

        provider_name = d.pop("provider_name", UNSET)

        user_identity_read = cls(
            id=id,
            user_id=user_id,
            identity_provider_id=identity_provider_id,
            issuer=issuer,
            subject=subject,
            created_at=created_at,
            updated_at=updated_at,
            last_used_at=last_used_at,
            provider_name=provider_name,
        )

        return user_identity_read
