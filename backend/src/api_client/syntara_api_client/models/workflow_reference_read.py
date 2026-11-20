from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="WorkflowReferenceRead")


@_attrs_define
class WorkflowReferenceRead:
    """A currently published parent workflow step that references this child.

    Attributes:
        workflow_id (UUID):
        workflow_name (str):
        workflow_version (int):
        step_id (str):
        step_name (None | str | Unset):
    """

    workflow_id: UUID
    workflow_name: str
    workflow_version: int
    step_id: str
    step_name: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        workflow_id = str(self.workflow_id)

        workflow_name = self.workflow_name

        workflow_version = self.workflow_version

        step_id = self.step_id

        step_name: None | str | Unset
        if isinstance(self.step_name, Unset):
            step_name = UNSET
        else:
            step_name = self.step_name

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "workflow_version": workflow_version,
                "step_id": step_id,
            }
        )
        if step_name is not UNSET:
            field_dict["step_name"] = step_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        workflow_id = UUID(d.pop("workflow_id"))

        workflow_name = d.pop("workflow_name")

        workflow_version = d.pop("workflow_version")

        step_id = d.pop("step_id")

        def _parse_step_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        step_name = _parse_step_name(d.pop("step_name", UNSET))

        workflow_reference_read = cls(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            step_id=step_id,
            step_name=step_name,
        )

        return workflow_reference_read
