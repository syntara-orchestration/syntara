from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_step_metadata_read_output_schema_type_0 import WorkflowStepMetadataReadOutputSchemaType0


T = TypeVar("T", bound="WorkflowStepMetadataRead")


@_attrs_define
class WorkflowStepMetadataRead:
    """Published workflow step metadata used by the variable picker.

    Attributes:
        id (str):
        type_ (str):
        output_schema (None | Unset | WorkflowStepMetadataReadOutputSchemaType0): JSON Schema for this step's output, or
            null when the step type has no output model.
    """

    id: str
    type_: str
    output_schema: None | Unset | WorkflowStepMetadataReadOutputSchemaType0 = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.workflow_step_metadata_read_output_schema_type_0 import WorkflowStepMetadataReadOutputSchemaType0

        id = self.id

        type_ = self.type_

        output_schema: dict[str, Any] | None | Unset
        if isinstance(self.output_schema, Unset):
            output_schema = UNSET
        elif isinstance(self.output_schema, WorkflowStepMetadataReadOutputSchemaType0):
            output_schema = self.output_schema.to_dict()
        else:
            output_schema = self.output_schema

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "type": type_,
            }
        )
        if output_schema is not UNSET:
            field_dict["output_schema"] = output_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_step_metadata_read_output_schema_type_0 import WorkflowStepMetadataReadOutputSchemaType0

        d = dict(src_dict)
        id = d.pop("id")

        type_ = d.pop("type")

        def _parse_output_schema(data: object) -> None | Unset | WorkflowStepMetadataReadOutputSchemaType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_schema_type_0 = WorkflowStepMetadataReadOutputSchemaType0.from_dict(data)

                return output_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | WorkflowStepMetadataReadOutputSchemaType0, data)

        output_schema = _parse_output_schema(d.pop("output_schema", UNSET))

        workflow_step_metadata_read = cls(
            id=id,
            type_=type_,
            output_schema=output_schema,
        )

        workflow_step_metadata_read.additional_properties = d
        return workflow_step_metadata_read

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
