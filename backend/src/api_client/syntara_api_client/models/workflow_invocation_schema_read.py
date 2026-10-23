from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.workflow_invocation_trigger_schema import WorkflowInvocationTriggerSchema


T = TypeVar("T", bound="WorkflowInvocationSchemaRead")


@_attrs_define
class WorkflowInvocationSchemaRead:
    """Published invocation schemas for a child workflow.

    Attributes:
        workflow_id (UUID):
        published_version_id (UUID):
        published_version (int):
        is_eligible (bool):
        triggers (list[WorkflowInvocationTriggerSchema]):
    """

    workflow_id: UUID
    published_version_id: UUID
    published_version: int
    is_eligible: bool
    triggers: list[WorkflowInvocationTriggerSchema]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        workflow_id = str(self.workflow_id)

        published_version_id = str(self.published_version_id)

        published_version = self.published_version

        is_eligible = self.is_eligible

        triggers = []
        for triggers_item_data in self.triggers:
            triggers_item = triggers_item_data.to_dict()
            triggers.append(triggers_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "workflow_id": workflow_id,
                "published_version_id": published_version_id,
                "published_version": published_version,
                "is_eligible": is_eligible,
                "triggers": triggers,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_invocation_trigger_schema import WorkflowInvocationTriggerSchema

        d = dict(src_dict)
        workflow_id = UUID(d.pop("workflow_id"))

        published_version_id = UUID(d.pop("published_version_id"))

        published_version = d.pop("published_version")

        is_eligible = d.pop("is_eligible")

        triggers = []
        _triggers = d.pop("triggers")
        for triggers_item_data in _triggers:
            triggers_item = WorkflowInvocationTriggerSchema.from_dict(triggers_item_data)

            triggers.append(triggers_item)

        workflow_invocation_schema_read = cls(
            workflow_id=workflow_id,
            published_version_id=published_version_id,
            published_version=published_version,
            is_eligible=is_eligible,
            triggers=triggers,
        )

        workflow_invocation_schema_read.additional_properties = d
        return workflow_invocation_schema_read

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
