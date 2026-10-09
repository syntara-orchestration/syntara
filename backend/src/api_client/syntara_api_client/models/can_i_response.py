from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="CanIResponse")


@_attrs_define
class CanIResponse:
    """Authorization decision result.

    Attributes:
        allowed (bool): Whether the action is allowed
        denied (bool): Whether the action is explicitly denied
        matched_policy (str): Name of the policy that matched
        denial_reason (str): Reason for denial (empty if allowed)
        denied_by (str): Name of the deny policy (empty if allowed)
    """

    allowed: bool
    denied: bool
    matched_policy: str
    denial_reason: str
    denied_by: str

    def to_dict(self) -> dict[str, Any]:
        allowed = self.allowed

        denied = self.denied

        matched_policy = self.matched_policy

        denial_reason = self.denial_reason

        denied_by = self.denied_by

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "allowed": allowed,
                "denied": denied,
                "matched_policy": matched_policy,
                "denial_reason": denial_reason,
                "denied_by": denied_by,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        allowed = d.pop("allowed")

        denied = d.pop("denied")

        matched_policy = d.pop("matched_policy")

        denial_reason = d.pop("denial_reason")

        denied_by = d.pop("denied_by")

        can_i_response = cls(
            allowed=allowed,
            denied=denied,
            matched_policy=matched_policy,
            denial_reason=denial_reason,
            denied_by=denied_by,
        )

        return can_i_response
