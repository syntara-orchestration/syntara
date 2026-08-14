from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.service_account_credential_read import ServiceAccountCredentialRead


T = TypeVar("T", bound="ServiceAccountCredentialListResponse")


@_attrs_define
class ServiceAccountCredentialListResponse:
    """Paginated list response for service account credentials.

    Attributes:
        resources (list[ServiceAccountCredentialRead]): Array of resources in current page
        next_ (None | str | Unset): Cursor for next page of results
        prev (None | str | Unset): Cursor for previous page of results
        total (int | None | Unset): Total count of resources (only when include_total=true)
        max_credentials (int | Unset): Maximum number of credentials allowed per service account Default: 10.
        total_credentials (int | Unset): Total number of credentials for this service account (ignoring filters)
            Default: 0.
        max_lifetime_days (int | Unset): Maximum credential lifetime in days (-1 for unlimited) Default: 180.
    """

    resources: list[ServiceAccountCredentialRead]
    next_: None | str | Unset = UNSET
    prev: None | str | Unset = UNSET
    total: int | None | Unset = UNSET
    max_credentials: int | Unset = 10
    total_credentials: int | Unset = 0
    max_lifetime_days: int | Unset = 180
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        resources = []
        for resources_item_data in self.resources:
            resources_item = resources_item_data.to_dict()
            resources.append(resources_item)

        next_: None | str | Unset
        if isinstance(self.next_, Unset):
            next_ = UNSET
        else:
            next_ = self.next_

        prev: None | str | Unset
        if isinstance(self.prev, Unset):
            prev = UNSET
        else:
            prev = self.prev

        total: int | None | Unset
        if isinstance(self.total, Unset):
            total = UNSET
        else:
            total = self.total

        max_credentials = self.max_credentials

        total_credentials = self.total_credentials

        max_lifetime_days = self.max_lifetime_days

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "resources": resources,
            }
        )
        if next_ is not UNSET:
            field_dict["next"] = next_
        if prev is not UNSET:
            field_dict["prev"] = prev
        if total is not UNSET:
            field_dict["total"] = total
        if max_credentials is not UNSET:
            field_dict["max_credentials"] = max_credentials
        if total_credentials is not UNSET:
            field_dict["total_credentials"] = total_credentials
        if max_lifetime_days is not UNSET:
            field_dict["max_lifetime_days"] = max_lifetime_days

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.service_account_credential_read import ServiceAccountCredentialRead

        d = dict(src_dict)
        resources = []
        _resources = d.pop("resources")
        for resources_item_data in _resources:
            resources_item = ServiceAccountCredentialRead.from_dict(resources_item_data)

            resources.append(resources_item)

        def _parse_next_(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        next_ = _parse_next_(d.pop("next", UNSET))

        def _parse_prev(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        prev = _parse_prev(d.pop("prev", UNSET))

        def _parse_total(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        total = _parse_total(d.pop("total", UNSET))

        max_credentials = d.pop("max_credentials", UNSET)

        total_credentials = d.pop("total_credentials", UNSET)

        max_lifetime_days = d.pop("max_lifetime_days", UNSET)

        service_account_credential_list_response = cls(
            resources=resources,
            next_=next_,
            prev=prev,
            total=total,
            max_credentials=max_credentials,
            total_credentials=total_credentials,
            max_lifetime_days=max_lifetime_days,
        )

        service_account_credential_list_response.additional_properties = d
        return service_account_credential_list_response

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
