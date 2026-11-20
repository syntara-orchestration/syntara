from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

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
        denied_scope (str | Unset): Scope of the denying policy statement Default: ''.
        denied_project (str | Unset): Project of the denying statement or missing grant Default: ''.
    """

    allowed: bool
    denied: bool
    matched_policy: str
    denial_reason: str
    denied_by: str
    denied_scope: str | Unset = ""
    denied_project: str | Unset = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        allowed = self.allowed

        denied = self.denied

        matched_policy = self.matched_policy

        denial_reason = self.denial_reason

        denied_by = self.denied_by

        denied_scope = self.denied_scope

        denied_project = self.denied_project

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "allowed": allowed,
                "denied": denied,
                "matched_policy": matched_policy,
                "denial_reason": denial_reason,
                "denied_by": denied_by,
            }
        )
        if denied_scope is not UNSET:
            field_dict["denied_scope"] = denied_scope
        if denied_project is not UNSET:
            field_dict["denied_project"] = denied_project

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        allowed = d.pop("allowed")

        denied = d.pop("denied")

        matched_policy = d.pop("matched_policy")

        denial_reason = d.pop("denial_reason")

        denied_by = d.pop("denied_by")

        denied_scope = d.pop("denied_scope", UNSET)

        denied_project = d.pop("denied_project", UNSET)

        can_i_response = cls(
            allowed=allowed,
            denied=denied,
            matched_policy=matched_policy,
            denial_reason=denial_reason,
            denied_by=denied_by,
            denied_scope=denied_scope,
            denied_project=denied_project,
        )

        can_i_response.additional_properties = d
        return can_i_response

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
