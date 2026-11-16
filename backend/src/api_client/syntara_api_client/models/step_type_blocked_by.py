from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="StepTypeBlockedBy")


@_attrs_define
class StepTypeBlockedBy:
    """Why the caller may not author one step type (the P2 Blocked step type shape).

    Attributes:
        kind: The step type identifier.
        label: Human-readable step type label.
        reason: ``explicit_deny`` when a deny policy matched, ``no_matching_allow``
            when no allow covers the kind.
        policy: Originating policy display name, or ``None`` for a missing allow.
        scope: Scope of the matching effective deny statement (``any`` or
            ``project``), or ``None`` for a missing allow.
        project: Project name for a project-scoped deny, ``None`` for a global
            deny (and for a missing allow, where the evaluated project name is
            reported instead).

        Attributes:
            kind (str):
            label (str):
            reason (str):
            policy (None | str | Unset):
            scope (None | str | Unset):
            project (None | str | Unset):
    """

    kind: str
    label: str
    reason: str
    policy: None | str | Unset = UNSET
    scope: None | str | Unset = UNSET
    project: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        label = self.label

        reason = self.reason

        policy: None | str | Unset
        if isinstance(self.policy, Unset):
            policy = UNSET
        else:
            policy = self.policy

        scope: None | str | Unset
        if isinstance(self.scope, Unset):
            scope = UNSET
        else:
            scope = self.scope

        project: None | str | Unset
        if isinstance(self.project, Unset):
            project = UNSET
        else:
            project = self.project

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "label": label,
                "reason": reason,
            }
        )
        if policy is not UNSET:
            field_dict["policy"] = policy
        if scope is not UNSET:
            field_dict["scope"] = scope
        if project is not UNSET:
            field_dict["project"] = project

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = d.pop("kind")

        label = d.pop("label")

        reason = d.pop("reason")

        def _parse_policy(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        policy = _parse_policy(d.pop("policy", UNSET))

        def _parse_scope(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        scope = _parse_scope(d.pop("scope", UNSET))

        def _parse_project(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        project = _parse_project(d.pop("project", UNSET))

        step_type_blocked_by = cls(
            kind=kind,
            label=label,
            reason=reason,
            policy=policy,
            scope=scope,
            project=project,
        )

        step_type_blocked_by.additional_properties = d
        return step_type_blocked_by

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
