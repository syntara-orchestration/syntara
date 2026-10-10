from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="CsrfTokenResponse")


@_attrs_define
class CsrfTokenResponse:
    """CSRF form token response.

    Attributes:
        csrf_token (str): CSRF form token for use in X-CSRF-Token header
    """

    csrf_token: str

    def to_dict(self) -> dict[str, Any]:
        csrf_token = self.csrf_token

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "csrf_token": csrf_token,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        csrf_token = d.pop("csrf_token")

        csrf_token_response = cls(
            csrf_token=csrf_token,
        )

        return csrf_token_response
