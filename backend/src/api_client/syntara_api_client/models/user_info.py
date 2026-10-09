from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="UserInfo")


@_attrs_define
class UserInfo:
    """Current user information derived from access token claims.

    Attributes:
        id (str): User UUID
        username (str): Username
        email (None | str | Unset): User email
        groups (list[str] | Unset): Group memberships
        rp_logout_enabled (bool | Unset): Whether RP-initiated logout is enabled for this user's current session
            Default: False.
    """

    id: str
    username: str
    email: None | str | Unset = UNSET
    groups: list[str] | Unset = UNSET
    rp_logout_enabled: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        username = self.username

        email: None | str | Unset
        if isinstance(self.email, Unset):
            email = UNSET
        else:
            email = self.email

        groups: list[str] | Unset = UNSET
        if not isinstance(self.groups, Unset):
            groups = self.groups

        rp_logout_enabled = self.rp_logout_enabled

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "username": username,
            }
        )
        if email is not UNSET:
            field_dict["email"] = email
        if groups is not UNSET:
            field_dict["groups"] = groups
        if rp_logout_enabled is not UNSET:
            field_dict["rp_logout_enabled"] = rp_logout_enabled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        username = d.pop("username")

        def _parse_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email = _parse_email(d.pop("email", UNSET))

        groups = cast(list[str], d.pop("groups", UNSET))

        rp_logout_enabled = d.pop("rp_logout_enabled", UNSET)

        user_info = cls(
            id=id,
            username=username,
            email=email,
            groups=groups,
            rp_logout_enabled=rp_logout_enabled,
        )

        return user_info
