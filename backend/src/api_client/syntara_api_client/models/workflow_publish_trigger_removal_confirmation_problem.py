from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="WorkflowPublishTriggerRemovalConfirmationProblem")


@_attrs_define
class WorkflowPublishTriggerRemovalConfirmationProblem:
    """Typed RFC 9457 problem body for the publish trigger-removal 409.

    Extends the base problem with the count of affected published parents (identities are never
    disclosed). Mirrors ``WorkflowPublishTriggerRemovalConfirmationProblem`` in the OpenAPI spec.

        Attributes:
            code (str): Machine-readable error code for programmatic handling
            detail (str): Human-readable explanation specific to this occurrence
            retryable (bool): Whether this error can be retried by creating a new invocation
            title (str): Short, human-readable summary of the problem
            type_ (str): URI reference identifying the problem type
            affected_count (int | None | Unset): Distinct published parents that invoke a Subworkflow Trigger removed by
                this publish.
            instance (None | str | Unset): Optional URI reference identifying the specific occurrence
    """

    code: str
    detail: str
    retryable: bool
    title: str
    type_: str
    affected_count: int | None | Unset = UNSET
    instance: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        detail = self.detail

        retryable = self.retryable

        title = self.title

        type_ = self.type_

        affected_count: int | None | Unset
        if isinstance(self.affected_count, Unset):
            affected_count = UNSET
        else:
            affected_count = self.affected_count

        instance: None | str | Unset
        if isinstance(self.instance, Unset):
            instance = UNSET
        else:
            instance = self.instance

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "detail": detail,
                "retryable": retryable,
                "title": title,
                "type": type_,
            }
        )
        if affected_count is not UNSET:
            field_dict["affected_count"] = affected_count
        if instance is not UNSET:
            field_dict["instance"] = instance

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = d.pop("code")

        detail = d.pop("detail")

        retryable = d.pop("retryable")

        title = d.pop("title")

        type_ = d.pop("type")

        def _parse_affected_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        affected_count = _parse_affected_count(d.pop("affected_count", UNSET))

        def _parse_instance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance = _parse_instance(d.pop("instance", UNSET))

        workflow_publish_trigger_removal_confirmation_problem = cls(
            code=code,
            detail=detail,
            retryable=retryable,
            title=title,
            type_=type_,
            affected_count=affected_count,
            instance=instance,
        )

        workflow_publish_trigger_removal_confirmation_problem.additional_properties = d
        return workflow_publish_trigger_removal_confirmation_problem

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
