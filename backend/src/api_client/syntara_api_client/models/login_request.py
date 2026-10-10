from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="LoginRequest")


@_attrs_define
class LoginRequest:
    """Login request with username and password.

    Attributes:
        username (str): Username
        password (str): Password
    """

    username: str
    password: str

    def to_dict(self) -> dict[str, Any]:
        username = self.username

        password = self.password

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "username": username,
                "password": password,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        username = d.pop("username")

        password = d.pop("password")

        login_request = cls(
            username=username,
            password=password,
        )

        return login_request
