from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.publish_version_request_workflow_definition_type_1 import PublishVersionRequestWorkflowDefinitionType1
    from ..models.workflow_definition import WorkflowDefinition


T = TypeVar("T", bound="PublishVersionRequest")


@_attrs_define
class PublishVersionRequest:
    """Request body for publishing a workflow version.

    Attributes:
        name (None | str | Unset): Optional name for this version
        change_description (None | str | Unset): Description of changes in this version
        workflow_definition (None | PublishVersionRequestWorkflowDefinitionType1 | Unset | WorkflowDefinition): Optional
            workflow definition to publish directly (skips separate save step)
        expected_version (int | None | Unset): Version the client was editing. If the server's current_version is
            higher, returns 409 Conflict.
    """

    name: None | str | Unset = UNSET
    change_description: None | str | Unset = UNSET
    workflow_definition: None | PublishVersionRequestWorkflowDefinitionType1 | Unset | WorkflowDefinition = UNSET
    expected_version: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.publish_version_request_workflow_definition_type_1 import (
            PublishVersionRequestWorkflowDefinitionType1,
        )
        from ..models.workflow_definition import WorkflowDefinition

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        change_description: None | str | Unset
        if isinstance(self.change_description, Unset):
            change_description = UNSET
        else:
            change_description = self.change_description

        workflow_definition: dict[str, Any] | None | Unset
        if isinstance(self.workflow_definition, Unset):
            workflow_definition = UNSET
        elif isinstance(self.workflow_definition, WorkflowDefinition):
            workflow_definition = self.workflow_definition.to_dict()
        elif isinstance(self.workflow_definition, PublishVersionRequestWorkflowDefinitionType1):
            workflow_definition = self.workflow_definition.to_dict()
        else:
            workflow_definition = self.workflow_definition

        expected_version: int | None | Unset
        if isinstance(self.expected_version, Unset):
            expected_version = UNSET
        else:
            expected_version = self.expected_version

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if change_description is not UNSET:
            field_dict["change_description"] = change_description
        if workflow_definition is not UNSET:
            field_dict["workflow_definition"] = workflow_definition
        if expected_version is not UNSET:
            field_dict["expected_version"] = expected_version

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.publish_version_request_workflow_definition_type_1 import (
            PublishVersionRequestWorkflowDefinitionType1,
        )
        from ..models.workflow_definition import WorkflowDefinition

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_change_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        change_description = _parse_change_description(d.pop("change_description", UNSET))

        def _parse_workflow_definition(
            data: object,
        ) -> None | PublishVersionRequestWorkflowDefinitionType1 | Unset | WorkflowDefinition:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                workflow_definition_type_0 = WorkflowDefinition.from_dict(data)

                return workflow_definition_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                workflow_definition_type_1 = PublishVersionRequestWorkflowDefinitionType1.from_dict(data)

                return workflow_definition_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PublishVersionRequestWorkflowDefinitionType1 | Unset | WorkflowDefinition, data)

        workflow_definition = _parse_workflow_definition(d.pop("workflow_definition", UNSET))

        def _parse_expected_version(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        expected_version = _parse_expected_version(d.pop("expected_version", UNSET))

        publish_version_request = cls(
            name=name,
            change_description=change_description,
            workflow_definition=workflow_definition,
            expected_version=expected_version,
        )

        return publish_version_request
