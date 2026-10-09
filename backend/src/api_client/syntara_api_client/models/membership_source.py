from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="MembershipSource")


@_attrs_define
class MembershipSource:
    """Describes how a user got membership in a group.

    Attributes:
        type_ (str): Source type: 'manual' or 'idp'
        provider_name (None | str | Unset): IdP name if source is 'idp'
        provider_id (None | Unset | UUID): IdP ID if source is 'idp'
    """

    type_: str
    provider_name: None | str | Unset = UNSET
    provider_id: None | Unset | UUID = UNSET

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        provider_name: None | str | Unset
        if isinstance(self.provider_name, Unset):
            provider_name = UNSET
        else:
            provider_name = self.provider_name

        provider_id: None | str | Unset
        if isinstance(self.provider_id, Unset):
            provider_id = UNSET
        elif isinstance(self.provider_id, UUID):
            provider_id = str(self.provider_id)
        else:
            provider_id = self.provider_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
            }
        )
        if provider_name is not UNSET:
            field_dict["provider_name"] = provider_name
        if provider_id is not UNSET:
            field_dict["provider_id"] = provider_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = d.pop("type")

        def _parse_provider_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_name = _parse_provider_name(d.pop("provider_name", UNSET))

        def _parse_provider_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                provider_id_type_0 = UUID(data)

                return provider_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        provider_id = _parse_provider_id(d.pop("provider_id", UNSET))

        membership_source = cls(
            type_=type_,
            provider_name=provider_name,
            provider_id=provider_id,
        )

        return membership_source
