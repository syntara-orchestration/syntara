from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_create_labels import WorkflowCreateLabels
    from ..models.workflow_create_workflow_definition_type_1 import WorkflowCreateWorkflowDefinitionType1
    from ..models.workflow_definition import WorkflowDefinition


T = TypeVar("T", bound="WorkflowCreate")


@_attrs_define
class WorkflowCreate:
    """Schema for creating a new workflow (POST /workflows).

    Excludes auto-generated fields: id, created_at, updated_at, created_by (set by backend).
    Pydantic tries to parse workflow_definition as WorkflowDefinition first;
    on failure, the raw dict falls through to the service-level validator.

        Attributes:
            name (str): Workflow name
            workflow_definition (WorkflowCreateWorkflowDefinitionType1 | WorkflowDefinition): Workflow definition object
            project_id (UUID): Project to assign workflow to
            description (None | str | Unset): Workflow description
            labels (WorkflowCreateLabels | Unset): Workflow labels
            is_import (bool | Unset): When true, unavailable LLM models are cleared with warnings instead of rejecting the
                request. Use when importing workflows from other instances. Default: False.
    """

    name: str
    workflow_definition: WorkflowCreateWorkflowDefinitionType1 | WorkflowDefinition
    project_id: UUID
    description: None | str | Unset = UNSET
    labels: WorkflowCreateLabels | Unset = UNSET
    is_import: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.workflow_definition import WorkflowDefinition

        name = self.name

        workflow_definition: dict[str, Any]
        if isinstance(self.workflow_definition, WorkflowDefinition):
            workflow_definition = self.workflow_definition.to_dict()
        else:
            workflow_definition = self.workflow_definition.to_dict()

        project_id = str(self.project_id)

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        is_import = self.is_import

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "workflow_definition": workflow_definition,
                "project_id": project_id,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if labels is not UNSET:
            field_dict["labels"] = labels
        if is_import is not UNSET:
            field_dict["is_import"] = is_import

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_create_labels import WorkflowCreateLabels
        from ..models.workflow_create_workflow_definition_type_1 import WorkflowCreateWorkflowDefinitionType1
        from ..models.workflow_definition import WorkflowDefinition

        d = dict(src_dict)
        name = d.pop("name")

        def _parse_workflow_definition(data: object) -> WorkflowCreateWorkflowDefinitionType1 | WorkflowDefinition:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                workflow_definition_type_0 = WorkflowDefinition.from_dict(data)

                return workflow_definition_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            workflow_definition_type_1 = WorkflowCreateWorkflowDefinitionType1.from_dict(data)

            return workflow_definition_type_1

        workflow_definition = _parse_workflow_definition(d.pop("workflow_definition"))

        project_id = UUID(d.pop("project_id"))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        _labels = d.pop("labels", UNSET)
        labels: WorkflowCreateLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = WorkflowCreateLabels.from_dict(_labels)

        is_import = d.pop("is_import", UNSET)

        workflow_create = cls(
            name=name,
            workflow_definition=workflow_definition,
            project_id=project_id,
            description=description,
            labels=labels,
            is_import=is_import,
        )

        workflow_create.additional_properties = d
        return workflow_create

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
