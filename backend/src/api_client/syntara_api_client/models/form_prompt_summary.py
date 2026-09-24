from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.form_prompt_status import FormPromptStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="FormPromptSummary")


@_attrs_define
class FormPromptSummary:
    """Minimal form prompt response for internal workflow engine endpoints.

    Contains only the 8 documented fields used by expire/cancel activities
    and workflow lifecycle management. Does not expose user-submitted form data
    or rendering configuration fields.

        Attributes:
            id (UUID): Form prompt unique identifier
            execution_id (UUID): Parent workflow execution ID
            project_id (UUID): Project ID (denormalized from execution)
            prompt_node_id (str): Canvas node ID from the workflow definition
            name (str): Display name for the form prompt
            status (FormPromptStatus): Form prompt status enumeration.
            temporal_activity_id (str): Temporal activity ID for async completion
            loop_iteration_path (list[int] | Unset): Enclosing-loop indices, outermost first
    """

    id: UUID
    execution_id: UUID
    project_id: UUID
    prompt_node_id: str
    name: str
    status: FormPromptStatus
    temporal_activity_id: str
    loop_iteration_path: list[int] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        execution_id = str(self.execution_id)

        project_id = str(self.project_id)

        prompt_node_id = self.prompt_node_id

        name = self.name

        status = self.status.value

        temporal_activity_id = self.temporal_activity_id

        loop_iteration_path: list[int] | Unset = UNSET
        if not isinstance(self.loop_iteration_path, Unset):
            loop_iteration_path = self.loop_iteration_path

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "execution_id": execution_id,
                "project_id": project_id,
                "prompt_node_id": prompt_node_id,
                "name": name,
                "status": status,
                "temporal_activity_id": temporal_activity_id,
            }
        )
        if loop_iteration_path is not UNSET:
            field_dict["loop_iteration_path"] = loop_iteration_path

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        execution_id = UUID(d.pop("execution_id"))

        project_id = UUID(d.pop("project_id"))

        prompt_node_id = d.pop("prompt_node_id")

        name = d.pop("name")

        status = FormPromptStatus(d.pop("status"))

        temporal_activity_id = d.pop("temporal_activity_id")

        loop_iteration_path = cast(list[int], d.pop("loop_iteration_path", UNSET))

        form_prompt_summary = cls(
            id=id,
            execution_id=execution_id,
            project_id=project_id,
            prompt_node_id=prompt_node_id,
            name=name,
            status=status,
            temporal_activity_id=temporal_activity_id,
            loop_iteration_path=loop_iteration_path,
        )

        form_prompt_summary.additional_properties = d
        return form_prompt_summary

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
