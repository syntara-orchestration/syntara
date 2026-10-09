from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="GlobalRevocationTimestampRead")


@_attrs_define
class GlobalRevocationTimestampRead:
    """Response schema for reading the global revocation timestamp.

    Attributes:
        revoked_before (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
        updated_by (None | str | Unset):
    """

    revoked_before: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    updated_by: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        revoked_before: None | str | Unset
        if isinstance(self.revoked_before, Unset):
            revoked_before = UNSET
        elif isinstance(self.revoked_before, datetime.datetime):
            revoked_before = self.revoked_before.isoformat()
        else:
            revoked_before = self.revoked_before

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        updated_by: None | str | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        else:
            updated_by = self.updated_by

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if revoked_before is not UNSET:
            field_dict["revoked_before"] = revoked_before
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_revoked_before(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                revoked_before_type_0 = isoparse(data)

                return revoked_before_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        revoked_before = _parse_revoked_before(d.pop("revoked_before", UNSET))

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

        def _parse_updated_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        global_revocation_timestamp_read = cls(
            revoked_before=revoked_before,
            updated_at=updated_at,
            updated_by=updated_by,
        )

        return global_revocation_timestamp_read
