from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.approval_node_parameters_fallback_decision_type_0 import ApprovalNodeParametersFallbackDecisionType0
from ..types import UNSET, Unset

T = TypeVar("T", bound="ApprovalNodeParameters")


@_attrs_define
class ApprovalNodeParameters:
    """Parameters for approval gate nodes.

    Attributes:
        credential_id (None | str | Unset): Orchestrator credential UUID
        approver_users (list[str] | None | Unset): Usernames who can approve
        approver_groups (list[str] | None | Unset): Group names whose members can approve
        prompt (None | str | Unset): Message to display to approvers
        fallback_decision (ApprovalNodeParametersFallbackDecisionType0 | None | Unset): Decision when approval times out
            with continue_on_failure
        decision_window (int | None | Unset): Response timeout in seconds
    """

    credential_id: None | str | Unset = UNSET
    approver_users: list[str] | None | Unset = UNSET
    approver_groups: list[str] | None | Unset = UNSET
    prompt: None | str | Unset = UNSET
    fallback_decision: ApprovalNodeParametersFallbackDecisionType0 | None | Unset = UNSET
    decision_window: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        credential_id: None | str | Unset
        if isinstance(self.credential_id, Unset):
            credential_id = UNSET
        else:
            credential_id = self.credential_id

        approver_users: list[str] | None | Unset
        if isinstance(self.approver_users, Unset):
            approver_users = UNSET
        elif isinstance(self.approver_users, list):
            approver_users = self.approver_users

        else:
            approver_users = self.approver_users

        approver_groups: list[str] | None | Unset
        if isinstance(self.approver_groups, Unset):
            approver_groups = UNSET
        elif isinstance(self.approver_groups, list):
            approver_groups = self.approver_groups

        else:
            approver_groups = self.approver_groups

        prompt: None | str | Unset
        if isinstance(self.prompt, Unset):
            prompt = UNSET
        else:
            prompt = self.prompt

        fallback_decision: None | str | Unset
        if isinstance(self.fallback_decision, Unset):
            fallback_decision = UNSET
        elif isinstance(self.fallback_decision, ApprovalNodeParametersFallbackDecisionType0):
            fallback_decision = self.fallback_decision.value
        else:
            fallback_decision = self.fallback_decision

        decision_window: int | None | Unset
        if isinstance(self.decision_window, Unset):
            decision_window = UNSET
        else:
            decision_window = self.decision_window

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if credential_id is not UNSET:
            field_dict["credential_id"] = credential_id
        if approver_users is not UNSET:
            field_dict["approver_users"] = approver_users
        if approver_groups is not UNSET:
            field_dict["approver_groups"] = approver_groups
        if prompt is not UNSET:
            field_dict["prompt"] = prompt
        if fallback_decision is not UNSET:
            field_dict["fallback_decision"] = fallback_decision
        if decision_window is not UNSET:
            field_dict["decision_window"] = decision_window

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_credential_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        credential_id = _parse_credential_id(d.pop("credential_id", UNSET))

        def _parse_approver_users(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                approver_users_type_0 = cast(list[str], data)

                return approver_users_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        approver_users = _parse_approver_users(d.pop("approver_users", UNSET))

        def _parse_approver_groups(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                approver_groups_type_0 = cast(list[str], data)

                return approver_groups_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        approver_groups = _parse_approver_groups(d.pop("approver_groups", UNSET))

        def _parse_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        prompt = _parse_prompt(d.pop("prompt", UNSET))

        def _parse_fallback_decision(data: object) -> ApprovalNodeParametersFallbackDecisionType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                fallback_decision_type_0 = ApprovalNodeParametersFallbackDecisionType0(data)

                return fallback_decision_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ApprovalNodeParametersFallbackDecisionType0 | None | Unset, data)

        fallback_decision = _parse_fallback_decision(d.pop("fallback_decision", UNSET))

        def _parse_decision_window(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        decision_window = _parse_decision_window(d.pop("decision_window", UNSET))

        approval_node_parameters = cls(
            credential_id=credential_id,
            approver_users=approver_users,
            approver_groups=approver_groups,
            prompt=prompt,
            fallback_decision=fallback_decision,
            decision_window=decision_window,
        )

        approval_node_parameters.additional_properties = d
        return approval_node_parameters

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
