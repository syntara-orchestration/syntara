from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.previous_step_context import PreviousStepContext
    from ..models.workflow_context_inputs import WorkflowContextInputs


T = TypeVar("T", bound="WorkflowContext")


@_attrs_define
class WorkflowContext:
    """Workflow Context for approvers.

    Essential context for approvers to make a decision.
    Contains workflow identification, inputs, and the output from the immediately
    preceding activity.

        Attributes:
            workflow_name (str): Name of the workflow
            inputs (WorkflowContextInputs): Original workflow input parameters (structure varies per workflow)
            workflow_id (None | Unset | UUID): ID of the workflow
            workflow_version (int | None | Unset): Integer version number of the workflow version executed
            previous_step (None | PreviousStepContext | Unset): Previous step context and output
    """

    workflow_name: str
    inputs: WorkflowContextInputs
    workflow_id: None | Unset | UUID = UNSET
    workflow_version: int | None | Unset = UNSET
    previous_step: None | PreviousStepContext | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.previous_step_context import PreviousStepContext

        workflow_name = self.workflow_name

        inputs = self.inputs.to_dict()

        workflow_id: None | str | Unset
        if isinstance(self.workflow_id, Unset):
            workflow_id = UNSET
        elif isinstance(self.workflow_id, UUID):
            workflow_id = str(self.workflow_id)
        else:
            workflow_id = self.workflow_id

        workflow_version: int | None | Unset
        if isinstance(self.workflow_version, Unset):
            workflow_version = UNSET
        else:
            workflow_version = self.workflow_version

        previous_step: dict[str, Any] | None | Unset
        if isinstance(self.previous_step, Unset):
            previous_step = UNSET
        elif isinstance(self.previous_step, PreviousStepContext):
            previous_step = self.previous_step.to_dict()
        else:
            previous_step = self.previous_step

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "workflow_name": workflow_name,
                "inputs": inputs,
            }
        )
        if workflow_id is not UNSET:
            field_dict["workflow_id"] = workflow_id
        if workflow_version is not UNSET:
            field_dict["workflow_version"] = workflow_version
        if previous_step is not UNSET:
            field_dict["previous_step"] = previous_step

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.previous_step_context import PreviousStepContext
        from ..models.workflow_context_inputs import WorkflowContextInputs

        d = dict(src_dict)
        workflow_name = d.pop("workflow_name")

        inputs = WorkflowContextInputs.from_dict(d.pop("inputs"))

        def _parse_workflow_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                workflow_id_type_0 = UUID(data)

                return workflow_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        workflow_id = _parse_workflow_id(d.pop("workflow_id", UNSET))

        def _parse_workflow_version(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        workflow_version = _parse_workflow_version(d.pop("workflow_version", UNSET))

        def _parse_previous_step(data: object) -> None | PreviousStepContext | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                previous_step_type_0 = PreviousStepContext.from_dict(data)

                return previous_step_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PreviousStepContext | Unset, data)

        previous_step = _parse_previous_step(d.pop("previous_step", UNSET))

        workflow_context = cls(
            workflow_name=workflow_name,
            inputs=inputs,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            previous_step=previous_step,
        )

        return workflow_context
