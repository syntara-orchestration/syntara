from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RevocationResponse")


@_attrs_define
class RevocationResponse:
    """Response schema for revocation operations.

    Attributes:
        message (str):
        sessions_revoked (int | None | Unset):
    """

    message: str
    sessions_revoked: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        sessions_revoked: int | None | Unset
        if isinstance(self.sessions_revoked, Unset):
            sessions_revoked = UNSET
        else:
            sessions_revoked = self.sessions_revoked

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "message": message,
            }
        )
        if sessions_revoked is not UNSET:
            field_dict["sessions_revoked"] = sessions_revoked

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message")

        def _parse_sessions_revoked(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        sessions_revoked = _parse_sessions_revoked(d.pop("sessions_revoked", UNSET))

        revocation_response = cls(
            message=message,
            sessions_revoked=sessions_revoked,
        )

        return revocation_response
