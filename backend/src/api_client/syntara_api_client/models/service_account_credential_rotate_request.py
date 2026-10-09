from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ServiceAccountCredentialRotateRequest")


@_attrs_define
class ServiceAccountCredentialRotateRequest:
    """Schema for rotating a credential's secret.

    Attributes:
        grace_period_seconds (int | None | Unset): Override grace period for this rotation (uses credential default if
            omitted)
    """

    grace_period_seconds: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        grace_period_seconds: int | None | Unset
        if isinstance(self.grace_period_seconds, Unset):
            grace_period_seconds = UNSET
        else:
            grace_period_seconds = self.grace_period_seconds

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if grace_period_seconds is not UNSET:
            field_dict["grace_period_seconds"] = grace_period_seconds

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_grace_period_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        grace_period_seconds = _parse_grace_period_seconds(d.pop("grace_period_seconds", UNSET))

        service_account_credential_rotate_request = cls(
            grace_period_seconds=grace_period_seconds,
        )

        return service_account_credential_rotate_request
