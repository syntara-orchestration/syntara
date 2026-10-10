from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="UserIdentityAttach")


@_attrs_define
class UserIdentityAttach:
    """Schema for attaching an identity to a user.

    Attributes:
        identity_id (UUID):
    """

    identity_id: UUID

    def to_dict(self) -> dict[str, Any]:
        identity_id = str(self.identity_id)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "identity_id": identity_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        identity_id = UUID(d.pop("identity_id"))

        user_identity_attach = cls(
            identity_id=identity_id,
        )

        return user_identity_attach
