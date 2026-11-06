from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.workflow_step_metadata_read import WorkflowStepMetadataRead


T = TypeVar("T", bound="PublishedWorkflowStepMetadataRead")


@_attrs_define
class PublishedWorkflowStepMetadataRead:
    """Step metadata tied to the exact published workflow version.

    Attributes:
        version_id (UUID):
        version (int):
        steps (list[WorkflowStepMetadataRead]):
    """

    version_id: UUID
    version: int
    steps: list[WorkflowStepMetadataRead]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        version_id = str(self.version_id)

        version = self.version

        steps = []
        for steps_item_data in self.steps:
            steps_item = steps_item_data.to_dict()
            steps.append(steps_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "version_id": version_id,
                "version": version,
                "steps": steps,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_step_metadata_read import WorkflowStepMetadataRead

        d = dict(src_dict)
        version_id = UUID(d.pop("version_id"))

        version = d.pop("version")

        steps = []
        _steps = d.pop("steps")
        for steps_item_data in _steps:
            steps_item = WorkflowStepMetadataRead.from_dict(steps_item_data)

            steps.append(steps_item)

        published_workflow_step_metadata_read = cls(
            version_id=version_id,
            version=version,
            steps=steps,
        )

        published_workflow_step_metadata_read.additional_properties = d
        return published_workflow_step_metadata_read

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
