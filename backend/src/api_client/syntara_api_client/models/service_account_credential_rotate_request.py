from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

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
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grace_period_seconds: int | None | Unset
        if isinstance(self.grace_period_seconds, Unset):
            grace_period_seconds = UNSET
        else:
            grace_period_seconds = self.grace_period_seconds

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
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

        service_account_credential_rotate_request.additional_properties = d
        return service_account_credential_rotate_request

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
