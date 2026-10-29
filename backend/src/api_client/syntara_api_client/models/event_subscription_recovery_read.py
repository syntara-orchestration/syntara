from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="EventSubscriptionRecoveryRead")


@_attrs_define
class EventSubscriptionRecoveryRead:
    """Safe queued recovery status; authority originates in the persisted request.

    Attributes:
        source_id (UUID):
        partition (int):
        configuration_revision (int):
        expected_recovery_revision (int):
        policy (str):
        reason (str):
        acknowledge_duplicate_risk (bool):
        resolve_unscheduled (bool):
        requested_by (UUID):
        completed (bool):
        error_code (None | str):
    """

    source_id: UUID
    partition: int
    configuration_revision: int
    expected_recovery_revision: int
    policy: str
    reason: str
    acknowledge_duplicate_risk: bool
    resolve_unscheduled: bool
    requested_by: UUID
    completed: bool
    error_code: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source_id = str(self.source_id)

        partition = self.partition

        configuration_revision = self.configuration_revision

        expected_recovery_revision = self.expected_recovery_revision

        policy = self.policy

        reason = self.reason

        acknowledge_duplicate_risk = self.acknowledge_duplicate_risk

        resolve_unscheduled = self.resolve_unscheduled

        requested_by = str(self.requested_by)

        completed = self.completed

        error_code: None | str
        error_code = self.error_code

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source_id": source_id,
                "partition": partition,
                "configuration_revision": configuration_revision,
                "expected_recovery_revision": expected_recovery_revision,
                "policy": policy,
                "reason": reason,
                "acknowledge_duplicate_risk": acknowledge_duplicate_risk,
                "resolve_unscheduled": resolve_unscheduled,
                "requested_by": requested_by,
                "completed": completed,
                "error_code": error_code,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source_id = UUID(d.pop("source_id"))

        partition = d.pop("partition")

        configuration_revision = d.pop("configuration_revision")

        expected_recovery_revision = d.pop("expected_recovery_revision")

        policy = d.pop("policy")

        reason = d.pop("reason")

        acknowledge_duplicate_risk = d.pop("acknowledge_duplicate_risk")

        resolve_unscheduled = d.pop("resolve_unscheduled")

        requested_by = UUID(d.pop("requested_by"))

        completed = d.pop("completed")

        def _parse_error_code(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        error_code = _parse_error_code(d.pop("error_code"))

        event_subscription_recovery_read = cls(
            source_id=source_id,
            partition=partition,
            configuration_revision=configuration_revision,
            expected_recovery_revision=expected_recovery_revision,
            policy=policy,
            reason=reason,
            acknowledge_duplicate_risk=acknowledge_duplicate_risk,
            resolve_unscheduled=resolve_unscheduled,
            requested_by=requested_by,
            completed=completed,
            error_code=error_code,
        )

        event_subscription_recovery_read.additional_properties = d
        return event_subscription_recovery_read

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
