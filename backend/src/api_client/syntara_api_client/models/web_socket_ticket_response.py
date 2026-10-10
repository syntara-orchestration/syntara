from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="WebSocketTicketResponse")


@_attrs_define
class WebSocketTicketResponse:
    """Response for the WebSocket ticket exchange endpoint.

    Attributes:
        ticket (str): Single-use opaque ticket for WebSocket connection
        expires_in (int): Ticket lifetime in seconds
    """

    ticket: str
    expires_in: int

    def to_dict(self) -> dict[str, Any]:
        ticket = self.ticket

        expires_in = self.expires_in

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "ticket": ticket,
                "expires_in": expires_in,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ticket = d.pop("ticket")

        expires_in = d.pop("expires_in")

        web_socket_ticket_response = cls(
            ticket=ticket,
            expires_in=expires_in,
        )

        return web_socket_ticket_response
