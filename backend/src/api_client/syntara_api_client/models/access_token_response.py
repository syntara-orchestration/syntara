from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AccessTokenResponse")


@_attrs_define
class AccessTokenResponse:
    """Access token response (refresh token is sent via HttpOnly cookie).

    Attributes:
        access_token (str): JWT access token
        expires_in (int): Access token lifetime in seconds
        token_type (str | Unset): Token type Default: 'Bearer'.
    """

    access_token: str
    expires_in: int
    token_type: str | Unset = "Bearer"

    def to_dict(self) -> dict[str, Any]:
        access_token = self.access_token

        expires_in = self.expires_in

        token_type = self.token_type

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "access_token": access_token,
                "expires_in": expires_in,
            }
        )
        if token_type is not UNSET:
            field_dict["token_type"] = token_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        access_token = d.pop("access_token")

        expires_in = d.pop("expires_in")

        token_type = d.pop("token_type", UNSET)

        access_token_response = cls(
            access_token=access_token,
            expires_in=expires_in,
            token_type=token_type,
        )

        return access_token_response
