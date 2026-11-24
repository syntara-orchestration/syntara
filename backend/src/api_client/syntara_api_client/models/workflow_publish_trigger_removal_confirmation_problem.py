from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

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
            affected_count (int): Distinct published parents that invoke a Subworkflow Trigger removed by this publish.
            code (Literal['WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED']): Machine-readable error code; fixed for
                this problem type.
            detail (str): Human-readable explanation specific to this occurrence
            retryable (bool): Whether this error can be retried by creating a new invocation
            title (str): Short, human-readable summary of the problem
            type_ (str): URI reference identifying the problem type
            instance (None | str | Unset): Optional URI reference identifying the specific occurrence
    """

    affected_count: int
    code: Literal["WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED"]
    detail: str
    retryable: bool
    title: str
    type_: str
    instance: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        affected_count = self.affected_count

        code = self.code

        detail = self.detail

        retryable = self.retryable

        title = self.title

        type_ = self.type_

        instance: None | str | Unset
        if isinstance(self.instance, Unset):
            instance = UNSET
        else:
            instance = self.instance

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "affected_count": affected_count,
                "code": code,
                "detail": detail,
                "retryable": retryable,
                "title": title,
                "type": type_,
            }
        )
        if instance is not UNSET:
            field_dict["instance"] = instance

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        affected_count = d.pop("affected_count")

        code = cast(Literal["WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED"], d.pop("code"))
        if code != "WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED":
            raise ValueError(
                f"code must match const 'WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED', got '{code}'"
            )

        detail = d.pop("detail")

        retryable = d.pop("retryable")

        title = d.pop("title")

        type_ = d.pop("type")

        def _parse_instance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance = _parse_instance(d.pop("instance", UNSET))

        workflow_publish_trigger_removal_confirmation_problem = cls(
            affected_count=affected_count,
            code=code,
            detail=detail,
            retryable=retryable,
            title=title,
            type_=type_,
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
