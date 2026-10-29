from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.recovery_policy import RecoveryPolicy
from ..types import UNSET, Unset

T = TypeVar("T", bound="SubscriptionRecoveryRequest")


@_attrs_define
class SubscriptionRecoveryRequest:
    """Boundary policy only; the assigned worker resolves the effective offset.

    Attributes:
        configuration_revision (int):
        source_generation (int):
        partition (int):
        expected_recovery_revision (int):
        policy (RecoveryPolicy): The two permitted administrative gap policies, not replay controls.
        reason (str):
        acknowledge_duplicate_risk (bool | Unset):  Default: False.
        resolve_unscheduled (bool | Unset):  Default: False.
    """

    configuration_revision: int
    source_generation: int
    partition: int
    expected_recovery_revision: int
    policy: RecoveryPolicy
    reason: str
    acknowledge_duplicate_risk: bool | Unset = False
    resolve_unscheduled: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        configuration_revision = self.configuration_revision

        source_generation = self.source_generation

        partition = self.partition

        expected_recovery_revision = self.expected_recovery_revision

        policy = self.policy.value

        reason = self.reason

        acknowledge_duplicate_risk = self.acknowledge_duplicate_risk

        resolve_unscheduled = self.resolve_unscheduled

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "configuration_revision": configuration_revision,
                "source_generation": source_generation,
                "partition": partition,
                "expected_recovery_revision": expected_recovery_revision,
                "policy": policy,
                "reason": reason,
            }
        )
        if acknowledge_duplicate_risk is not UNSET:
            field_dict["acknowledge_duplicate_risk"] = acknowledge_duplicate_risk
        if resolve_unscheduled is not UNSET:
            field_dict["resolve_unscheduled"] = resolve_unscheduled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        configuration_revision = d.pop("configuration_revision")

        source_generation = d.pop("source_generation")

        partition = d.pop("partition")

        expected_recovery_revision = d.pop("expected_recovery_revision")

        policy = RecoveryPolicy(d.pop("policy"))

        reason = d.pop("reason")

        acknowledge_duplicate_risk = d.pop("acknowledge_duplicate_risk", UNSET)

        resolve_unscheduled = d.pop("resolve_unscheduled", UNSET)

        subscription_recovery_request = cls(
            configuration_revision=configuration_revision,
            source_generation=source_generation,
            partition=partition,
            expected_recovery_revision=expected_recovery_revision,
            policy=policy,
            reason=reason,
            acknowledge_duplicate_risk=acknowledge_duplicate_risk,
            resolve_unscheduled=resolve_unscheduled,
        )

        return subscription_recovery_request
