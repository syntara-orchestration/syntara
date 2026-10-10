from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.auth_type import AuthType
from ..types import UNSET, Unset

T = TypeVar("T", bound="UserRead")


@_attrs_define
class UserRead:
    """Schema for user response (GET /users/{id}).

    Includes all user fields except sensitive data (password_hash, preferences).

        Attributes:
            id (UUID):
            username (str):
            first_name (str):
            is_enabled (bool):
            created_at (datetime.datetime):
            updated_at (datetime.datetime):
            email (None | str | Unset):
            last_name (None | str | Unset):
            is_builtin (bool | Unset):  Default: False.
            auth_type (AuthType | Unset): Authentication type for users.
            auth_sources (list[str] | Unset):
            last_login (datetime.datetime | None | Unset):
    """

    id: UUID
    username: str
    first_name: str
    is_enabled: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    email: None | str | Unset = UNSET
    last_name: None | str | Unset = UNSET
    is_builtin: bool | Unset = False
    auth_type: AuthType | Unset = UNSET
    auth_sources: list[str] | Unset = UNSET
    last_login: datetime.datetime | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        username = self.username

        first_name = self.first_name

        is_enabled = self.is_enabled

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        email: None | str | Unset
        if isinstance(self.email, Unset):
            email = UNSET
        else:
            email = self.email

        last_name: None | str | Unset
        if isinstance(self.last_name, Unset):
            last_name = UNSET
        else:
            last_name = self.last_name

        is_builtin = self.is_builtin

        auth_type: str | Unset = UNSET
        if not isinstance(self.auth_type, Unset):
            auth_type = self.auth_type.value

        auth_sources: list[str] | Unset = UNSET
        if not isinstance(self.auth_sources, Unset):
            auth_sources = self.auth_sources

        last_login: None | str | Unset
        if isinstance(self.last_login, Unset):
            last_login = UNSET
        elif isinstance(self.last_login, datetime.datetime):
            last_login = self.last_login.isoformat()
        else:
            last_login = self.last_login

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "username": username,
                "first_name": first_name,
                "is_enabled": is_enabled,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if email is not UNSET:
            field_dict["email"] = email
        if last_name is not UNSET:
            field_dict["last_name"] = last_name
        if is_builtin is not UNSET:
            field_dict["is_builtin"] = is_builtin
        if auth_type is not UNSET:
            field_dict["auth_type"] = auth_type
        if auth_sources is not UNSET:
            field_dict["auth_sources"] = auth_sources
        if last_login is not UNSET:
            field_dict["last_login"] = last_login

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        username = d.pop("username")

        first_name = d.pop("first_name")

        is_enabled = d.pop("is_enabled")

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email = _parse_email(d.pop("email", UNSET))

        def _parse_last_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_name = _parse_last_name(d.pop("last_name", UNSET))

        is_builtin = d.pop("is_builtin", UNSET)

        _auth_type = d.pop("auth_type", UNSET)
        auth_type: AuthType | Unset
        if isinstance(_auth_type, Unset):
            auth_type = UNSET
        else:
            auth_type = AuthType(_auth_type)

        auth_sources = cast(list[str], d.pop("auth_sources", UNSET))

        def _parse_last_login(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_login_type_0 = isoparse(data)

                return last_login_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_login = _parse_last_login(d.pop("last_login", UNSET))

        user_read = cls(
            id=id,
            username=username,
            first_name=first_name,
            is_enabled=is_enabled,
            created_at=created_at,
            updated_at=updated_at,
            email=email,
            last_name=last_name,
            is_builtin=is_builtin,
            auth_type=auth_type,
            auth_sources=auth_sources,
            last_login=last_login,
        )

        return user_read
