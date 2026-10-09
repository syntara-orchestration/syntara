from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="WebhookResponse")


@_attrs_define
class WebhookResponse:
    """Response from webhook reception endpoint.

    Attributes:
        execution_id (UUID): ID of the triggered workflow execution
        message (str): Human-readable status message
    """

    execution_id: UUID
    message: str

    def to_dict(self) -> dict[str, Any]:
        execution_id = str(self.execution_id)

        message = self.message

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "execution_id": execution_id,
                "message": message,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        execution_id = UUID(d.pop("execution_id"))

        message = d.pop("message")

        webhook_response = cls(
            execution_id=execution_id,
            message=message,
        )

        return webhook_response
