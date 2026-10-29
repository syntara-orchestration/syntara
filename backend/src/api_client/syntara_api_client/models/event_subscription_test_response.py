from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.event_subscription_test_response_connection import EventSubscriptionTestResponseConnection
from ..models.event_subscription_test_response_topic_metadata import EventSubscriptionTestResponseTopicMetadata
from ..types import UNSET, Unset

T = TypeVar("T", bound="EventSubscriptionTestResponse")


@_attrs_define
class EventSubscriptionTestResponse:
    """Success proves connectivity and topic metadata only, never runtime ACLs.

    Attributes:
        success (bool):
        checked_at (datetime.datetime):
        connection (EventSubscriptionTestResponseConnection | Unset):  Default:
            EventSubscriptionTestResponseConnection.UNVERIFIED.
        topic_metadata (EventSubscriptionTestResponseTopicMetadata | Unset):  Default:
            EventSubscriptionTestResponseTopicMetadata.UNVERIFIED.
        topic_read (Literal['unverified'] | Unset):  Default: 'unverified'.
        group_access (Literal['unverified'] | Unset):  Default: 'unverified'.
        error_code (None | str | Unset): Sanitized failure code; no broker error text
    """

    success: bool
    checked_at: datetime.datetime
    connection: EventSubscriptionTestResponseConnection | Unset = EventSubscriptionTestResponseConnection.UNVERIFIED
    topic_metadata: EventSubscriptionTestResponseTopicMetadata | Unset = (
        EventSubscriptionTestResponseTopicMetadata.UNVERIFIED
    )
    topic_read: Literal["unverified"] | Unset = "unverified"
    group_access: Literal["unverified"] | Unset = "unverified"
    error_code: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        success = self.success

        checked_at = self.checked_at.isoformat()

        connection: str | Unset = UNSET
        if not isinstance(self.connection, Unset):
            connection = self.connection.value

        topic_metadata: str | Unset = UNSET
        if not isinstance(self.topic_metadata, Unset):
            topic_metadata = self.topic_metadata.value

        topic_read = self.topic_read

        group_access = self.group_access

        error_code: None | str | Unset
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        else:
            error_code = self.error_code

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "success": success,
                "checked_at": checked_at,
            }
        )
        if connection is not UNSET:
            field_dict["connection"] = connection
        if topic_metadata is not UNSET:
            field_dict["topic_metadata"] = topic_metadata
        if topic_read is not UNSET:
            field_dict["topic_read"] = topic_read
        if group_access is not UNSET:
            field_dict["group_access"] = group_access
        if error_code is not UNSET:
            field_dict["error_code"] = error_code

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        success = d.pop("success")

        checked_at = isoparse(d.pop("checked_at"))

        _connection = d.pop("connection", UNSET)
        connection: EventSubscriptionTestResponseConnection | Unset
        if isinstance(_connection, Unset):
            connection = UNSET
        else:
            connection = EventSubscriptionTestResponseConnection(_connection)

        _topic_metadata = d.pop("topic_metadata", UNSET)
        topic_metadata: EventSubscriptionTestResponseTopicMetadata | Unset
        if isinstance(_topic_metadata, Unset):
            topic_metadata = UNSET
        else:
            topic_metadata = EventSubscriptionTestResponseTopicMetadata(_topic_metadata)

        topic_read = cast(Literal["unverified"] | Unset, d.pop("topic_read", UNSET))
        if topic_read != "unverified" and not isinstance(topic_read, Unset):
            raise ValueError(f"topic_read must match const 'unverified', got '{topic_read}'")

        group_access = cast(Literal["unverified"] | Unset, d.pop("group_access", UNSET))
        if group_access != "unverified" and not isinstance(group_access, Unset):
            raise ValueError(f"group_access must match const 'unverified', got '{group_access}'")

        def _parse_error_code(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        event_subscription_test_response = cls(
            success=success,
            checked_at=checked_at,
            connection=connection,
            topic_metadata=topic_metadata,
            topic_read=topic_read,
            group_access=group_access,
            error_code=error_code,
        )

        event_subscription_test_response.additional_properties = d
        return event_subscription_test_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
