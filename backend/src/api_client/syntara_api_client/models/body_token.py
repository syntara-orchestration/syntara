from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="BodyToken")


@_attrs_define
class BodyToken:
    """
    Attributes:
        grant_type (str):
        client_id (str | Unset):  Default: ''.
        client_secret (str | Unset):  Default: ''.
    """

    grant_type: str
    client_id: str | Unset = ""
    client_secret: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        grant_type = self.grant_type

        client_id = self.client_id

        client_secret = self.client_secret

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "grant_type": grant_type,
            }
        )
        if client_id is not UNSET:
            field_dict["client_id"] = client_id
        if client_secret is not UNSET:
            field_dict["client_secret"] = client_secret

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        grant_type = d.pop("grant_type")

        client_id = d.pop("client_id", UNSET)

        client_secret = d.pop("client_secret", UNSET)

        body_token = cls(
            grant_type=grant_type,
            client_id=client_id,
            client_secret=client_secret,
        )

        return body_token
