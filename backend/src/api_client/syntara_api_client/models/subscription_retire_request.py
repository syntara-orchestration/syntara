from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SubscriptionRetireRequest")


@_attrs_define
class SubscriptionRetireRequest:
    """Safe retirement by default; disposition requires its separate grant.

    Attributes:
        configuration_revision (int):
        source_generation (int):
        reason (str):
        resolve_unscheduled (bool | Unset):  Default: False.
    """

    configuration_revision: int
    source_generation: int
    reason: str
    resolve_unscheduled: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        configuration_revision = self.configuration_revision

        source_generation = self.source_generation

        reason = self.reason

        resolve_unscheduled = self.resolve_unscheduled

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "configuration_revision": configuration_revision,
                "source_generation": source_generation,
                "reason": reason,
            }
        )
        if resolve_unscheduled is not UNSET:
            field_dict["resolve_unscheduled"] = resolve_unscheduled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        configuration_revision = d.pop("configuration_revision")

        source_generation = d.pop("source_generation")

        reason = d.pop("reason")

        resolve_unscheduled = d.pop("resolve_unscheduled", UNSET)

        subscription_retire_request = cls(
            configuration_revision=configuration_revision,
            source_generation=source_generation,
            reason=reason,
            resolve_unscheduled=resolve_unscheduled,
        )

        return subscription_retire_request
