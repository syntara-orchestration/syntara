from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.previous_step_context_output_type_0 import PreviousStepContextOutputType0


T = TypeVar("T", bound="PreviousStepContext")


@_attrs_define
class PreviousStepContext:
    """Previous Step Context for workflow execution.

    The activity that immediately preceded this approval node, including its output.
    Null if the approval node is the first activity in the workflow.

        Attributes:
            id (str): Activity ID from workflow definition
            name (str): Human-readable activity name
            type_ (str): Activity type (task, approval, parallel, etc.)
            output (None | PreviousStepContextOutputType0 | Unset): Output from the activity (structure varies per activity
                type)
    """

    id: str
    name: str
    type_: str
    output: None | PreviousStepContextOutputType0 | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.previous_step_context_output_type_0 import PreviousStepContextOutputType0

        id = self.id

        name = self.name

        type_ = self.type_

        output: dict[str, Any] | None | Unset
        if isinstance(self.output, Unset):
            output = UNSET
        elif isinstance(self.output, PreviousStepContextOutputType0):
            output = self.output.to_dict()
        else:
            output = self.output

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "name": name,
                "type": type_,
            }
        )
        if output is not UNSET:
            field_dict["output"] = output

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.previous_step_context_output_type_0 import PreviousStepContextOutputType0

        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        type_ = d.pop("type")

        def _parse_output(data: object) -> None | PreviousStepContextOutputType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_type_0 = PreviousStepContextOutputType0.from_dict(data)

                return output_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PreviousStepContextOutputType0 | Unset, data)

        output = _parse_output(d.pop("output", UNSET))

        previous_step_context = cls(
            id=id,
            name=name,
            type_=type_,
            output=output,
        )

        return previous_step_context
