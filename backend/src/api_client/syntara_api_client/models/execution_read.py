from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.execution_mode import ExecutionMode
from ..models.execution_status import ExecutionStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.activity_data import ActivityData
    from ..models.current_activity import CurrentActivity
    from ..models.execution_read_execution_metadata_type_0 import ExecutionReadExecutionMetadataType0
    from ..models.execution_read_input_data import ExecutionReadInputData
    from ..models.execution_read_labels import ExecutionReadLabels
    from ..models.workflow_definition import WorkflowDefinition


T = TypeVar("T", bound="ExecutionRead")


@_attrs_define
class ExecutionRead:
    """Schema for execution response (GET /executions/{id}).

    Includes database table fields plus computed fields (workflow_version,
    workflow_version_name, workflow_version_created_at) populated
    by ExecutionsConvertResourceMixin from the related WorkflowVersion.

        Attributes:
            id (UUID):
            workflow_id (UUID):
            workflow_version_id (UUID):
            project_id (UUID):
            temporal_workflow_id (str):
            status (ExecutionStatus): Current state of a workflow execution lifecycle.
            created_by (UUID):
            created_at (datetime.datetime):
            completed_at (datetime.datetime | None):
            updated_at (datetime.datetime):
            updated_by (None | UUID):
            input_data (ExecutionReadInputData):
            error_details (None | str):
            workflow_name (None | str | Unset): Name of the workflow
            workflow_version (int | None | Unset): Version number of the workflow version that was executed
            workflow_version_name (None | str | Unset): Name of the executed version, if one was set
            workflow_version_created_at (datetime.datetime | None | Unset): Timestamp when the executed version was created
            trigger_node_id (None | str | Unset):
            mode (ExecutionMode | Unset): Execution mode for workflow runs.
            execution_metadata (ExecutionReadExecutionMetadataType0 | None | Unset):
            retried_from_execution_id (None | Unset | UUID):
            trigger_type (None | str | Unset): Trigger node type (manual_trigger, scheduled_trigger, webhook_trigger,
                eda_trigger)
            interface (None | str | Unset): Originating interface (ui or api)
            labels (ExecutionReadLabels | Unset):
            approval_pending (bool | Unset):  Default: False.
            current_activities (list[CurrentActivity] | Unset): Currently executing activities
            workflow_definition (None | Unset | WorkflowDefinition): Workflow definition from the executed version. Only
                included when requested via ?include=workflow_definition query parameter.
            activities (list[ActivityData] | None | Unset): List of activities with their current status. Only included when
                requested via ?include=activities query parameter.
    """

    id: UUID
    workflow_id: UUID
    workflow_version_id: UUID
    project_id: UUID
    temporal_workflow_id: str
    status: ExecutionStatus
    created_by: UUID
    created_at: datetime.datetime
    completed_at: datetime.datetime | None
    updated_at: datetime.datetime
    updated_by: None | UUID
    input_data: ExecutionReadInputData
    error_details: None | str
    workflow_name: None | str | Unset = UNSET
    workflow_version: int | None | Unset = UNSET
    workflow_version_name: None | str | Unset = UNSET
    workflow_version_created_at: datetime.datetime | None | Unset = UNSET
    trigger_node_id: None | str | Unset = UNSET
    mode: ExecutionMode | Unset = UNSET
    execution_metadata: ExecutionReadExecutionMetadataType0 | None | Unset = UNSET
    retried_from_execution_id: None | Unset | UUID = UNSET
    trigger_type: None | str | Unset = UNSET
    interface: None | str | Unset = UNSET
    labels: ExecutionReadLabels | Unset = UNSET
    approval_pending: bool | Unset = False
    current_activities: list[CurrentActivity] | Unset = UNSET
    workflow_definition: None | Unset | WorkflowDefinition = UNSET
    activities: list[ActivityData] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.execution_read_execution_metadata_type_0 import ExecutionReadExecutionMetadataType0
        from ..models.workflow_definition import WorkflowDefinition

        id = str(self.id)

        workflow_id = str(self.workflow_id)

        workflow_version_id = str(self.workflow_version_id)

        project_id = str(self.project_id)

        temporal_workflow_id = self.temporal_workflow_id

        status = self.status.value

        created_by = str(self.created_by)

        created_at = self.created_at.isoformat()

        completed_at: None | str
        if isinstance(self.completed_at, datetime.datetime):
            completed_at = self.completed_at.isoformat()
        else:
            completed_at = self.completed_at

        updated_at = self.updated_at.isoformat()

        updated_by: None | str
        if isinstance(self.updated_by, UUID):
            updated_by = str(self.updated_by)
        else:
            updated_by = self.updated_by

        input_data = self.input_data.to_dict()

        error_details: None | str
        error_details = self.error_details

        workflow_name: None | str | Unset
        if isinstance(self.workflow_name, Unset):
            workflow_name = UNSET
        else:
            workflow_name = self.workflow_name

        workflow_version: int | None | Unset
        if isinstance(self.workflow_version, Unset):
            workflow_version = UNSET
        else:
            workflow_version = self.workflow_version

        workflow_version_name: None | str | Unset
        if isinstance(self.workflow_version_name, Unset):
            workflow_version_name = UNSET
        else:
            workflow_version_name = self.workflow_version_name

        workflow_version_created_at: None | str | Unset
        if isinstance(self.workflow_version_created_at, Unset):
            workflow_version_created_at = UNSET
        elif isinstance(self.workflow_version_created_at, datetime.datetime):
            workflow_version_created_at = self.workflow_version_created_at.isoformat()
        else:
            workflow_version_created_at = self.workflow_version_created_at

        trigger_node_id: None | str | Unset
        if isinstance(self.trigger_node_id, Unset):
            trigger_node_id = UNSET
        else:
            trigger_node_id = self.trigger_node_id

        mode: str | Unset = UNSET
        if not isinstance(self.mode, Unset):
            mode = self.mode.value

        execution_metadata: dict[str, Any] | None | Unset
        if isinstance(self.execution_metadata, Unset):
            execution_metadata = UNSET
        elif isinstance(self.execution_metadata, ExecutionReadExecutionMetadataType0):
            execution_metadata = self.execution_metadata.to_dict()
        else:
            execution_metadata = self.execution_metadata

        retried_from_execution_id: None | str | Unset
        if isinstance(self.retried_from_execution_id, Unset):
            retried_from_execution_id = UNSET
        elif isinstance(self.retried_from_execution_id, UUID):
            retried_from_execution_id = str(self.retried_from_execution_id)
        else:
            retried_from_execution_id = self.retried_from_execution_id

        trigger_type: None | str | Unset
        if isinstance(self.trigger_type, Unset):
            trigger_type = UNSET
        else:
            trigger_type = self.trigger_type

        interface: None | str | Unset
        if isinstance(self.interface, Unset):
            interface = UNSET
        else:
            interface = self.interface

        labels: dict[str, Any] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        approval_pending = self.approval_pending

        current_activities: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.current_activities, Unset):
            current_activities = []
            for current_activities_item_data in self.current_activities:
                current_activities_item = current_activities_item_data.to_dict()
                current_activities.append(current_activities_item)

        workflow_definition: dict[str, Any] | None | Unset
        if isinstance(self.workflow_definition, Unset):
            workflow_definition = UNSET
        elif isinstance(self.workflow_definition, WorkflowDefinition):
            workflow_definition = self.workflow_definition.to_dict()
        else:
            workflow_definition = self.workflow_definition

        activities: list[dict[str, Any]] | None | Unset
        if isinstance(self.activities, Unset):
            activities = UNSET
        elif isinstance(self.activities, list):
            activities = []
            for activities_type_0_item_data in self.activities:
                activities_type_0_item = activities_type_0_item_data.to_dict()
                activities.append(activities_type_0_item)

        else:
            activities = self.activities

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workflow_id": workflow_id,
                "workflow_version_id": workflow_version_id,
                "project_id": project_id,
                "temporal_workflow_id": temporal_workflow_id,
                "status": status,
                "created_by": created_by,
                "created_at": created_at,
                "completed_at": completed_at,
                "updated_at": updated_at,
                "updated_by": updated_by,
                "input_data": input_data,
                "error_details": error_details,
            }
        )
        if workflow_name is not UNSET:
            field_dict["workflow_name"] = workflow_name
        if workflow_version is not UNSET:
            field_dict["workflow_version"] = workflow_version
        if workflow_version_name is not UNSET:
            field_dict["workflow_version_name"] = workflow_version_name
        if workflow_version_created_at is not UNSET:
            field_dict["workflow_version_created_at"] = workflow_version_created_at
        if trigger_node_id is not UNSET:
            field_dict["trigger_node_id"] = trigger_node_id
        if mode is not UNSET:
            field_dict["mode"] = mode
        if execution_metadata is not UNSET:
            field_dict["execution_metadata"] = execution_metadata
        if retried_from_execution_id is not UNSET:
            field_dict["retried_from_execution_id"] = retried_from_execution_id
        if trigger_type is not UNSET:
            field_dict["trigger_type"] = trigger_type
        if interface is not UNSET:
            field_dict["interface"] = interface
        if labels is not UNSET:
            field_dict["labels"] = labels
        if approval_pending is not UNSET:
            field_dict["approval_pending"] = approval_pending
        if current_activities is not UNSET:
            field_dict["current_activities"] = current_activities
        if workflow_definition is not UNSET:
            field_dict["workflow_definition"] = workflow_definition
        if activities is not UNSET:
            field_dict["activities"] = activities

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.activity_data import ActivityData
        from ..models.current_activity import CurrentActivity
        from ..models.execution_read_execution_metadata_type_0 import ExecutionReadExecutionMetadataType0
        from ..models.execution_read_input_data import ExecutionReadInputData
        from ..models.execution_read_labels import ExecutionReadLabels
        from ..models.workflow_definition import WorkflowDefinition

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        workflow_id = UUID(d.pop("workflow_id"))

        workflow_version_id = UUID(d.pop("workflow_version_id"))

        project_id = UUID(d.pop("project_id"))

        temporal_workflow_id = d.pop("temporal_workflow_id")

        status = ExecutionStatus(d.pop("status"))

        created_by = UUID(d.pop("created_by"))

        created_at = isoparse(d.pop("created_at"))

        def _parse_completed_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                completed_at_type_0 = isoparse(data)

                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        completed_at = _parse_completed_at(d.pop("completed_at"))

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_updated_by(data: object) -> None | UUID:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_by_type_0 = UUID(data)

                return updated_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UUID, data)

        updated_by = _parse_updated_by(d.pop("updated_by"))

        input_data = ExecutionReadInputData.from_dict(d.pop("input_data"))

        def _parse_error_details(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        error_details = _parse_error_details(d.pop("error_details"))

        def _parse_workflow_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        workflow_name = _parse_workflow_name(d.pop("workflow_name", UNSET))

        def _parse_workflow_version(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        workflow_version = _parse_workflow_version(d.pop("workflow_version", UNSET))

        def _parse_workflow_version_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        workflow_version_name = _parse_workflow_version_name(d.pop("workflow_version_name", UNSET))

        def _parse_workflow_version_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                workflow_version_created_at_type_0 = isoparse(data)

                return workflow_version_created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        workflow_version_created_at = _parse_workflow_version_created_at(d.pop("workflow_version_created_at", UNSET))

        def _parse_trigger_node_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trigger_node_id = _parse_trigger_node_id(d.pop("trigger_node_id", UNSET))

        _mode = d.pop("mode", UNSET)
        mode: ExecutionMode | Unset
        if isinstance(_mode, Unset):
            mode = UNSET
        else:
            mode = ExecutionMode(_mode)

        def _parse_execution_metadata(data: object) -> ExecutionReadExecutionMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                execution_metadata_type_0 = ExecutionReadExecutionMetadataType0.from_dict(data)

                return execution_metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ExecutionReadExecutionMetadataType0 | None | Unset, data)

        execution_metadata = _parse_execution_metadata(d.pop("execution_metadata", UNSET))

        def _parse_retried_from_execution_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                retried_from_execution_id_type_0 = UUID(data)

                return retried_from_execution_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        retried_from_execution_id = _parse_retried_from_execution_id(d.pop("retried_from_execution_id", UNSET))

        def _parse_trigger_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trigger_type = _parse_trigger_type(d.pop("trigger_type", UNSET))

        def _parse_interface(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        interface = _parse_interface(d.pop("interface", UNSET))

        _labels = d.pop("labels", UNSET)
        labels: ExecutionReadLabels | Unset
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = ExecutionReadLabels.from_dict(_labels)

        approval_pending = d.pop("approval_pending", UNSET)

        _current_activities = d.pop("current_activities", UNSET)
        current_activities: list[CurrentActivity] | Unset = UNSET
        if _current_activities is not UNSET:
            current_activities = []
            for current_activities_item_data in _current_activities:
                current_activities_item = CurrentActivity.from_dict(current_activities_item_data)

                current_activities.append(current_activities_item)

        def _parse_workflow_definition(data: object) -> None | Unset | WorkflowDefinition:
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
            return cast(None | Unset | WorkflowDefinition, data)

        workflow_definition = _parse_workflow_definition(d.pop("workflow_definition", UNSET))

        def _parse_activities(data: object) -> list[ActivityData] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                activities_type_0 = []
                _activities_type_0 = data
                for activities_type_0_item_data in _activities_type_0:
                    activities_type_0_item = ActivityData.from_dict(activities_type_0_item_data)

                    activities_type_0.append(activities_type_0_item)

                return activities_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ActivityData] | None | Unset, data)

        activities = _parse_activities(d.pop("activities", UNSET))

        execution_read = cls(
            id=id,
            workflow_id=workflow_id,
            workflow_version_id=workflow_version_id,
            project_id=project_id,
            temporal_workflow_id=temporal_workflow_id,
            status=status,
            created_by=created_by,
            created_at=created_at,
            completed_at=completed_at,
            updated_at=updated_at,
            updated_by=updated_by,
            input_data=input_data,
            error_details=error_details,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            workflow_version_name=workflow_version_name,
            workflow_version_created_at=workflow_version_created_at,
            trigger_node_id=trigger_node_id,
            mode=mode,
            execution_metadata=execution_metadata,
            retried_from_execution_id=retried_from_execution_id,
            trigger_type=trigger_type,
            interface=interface,
            labels=labels,
            approval_pending=approval_pending,
            current_activities=current_activities,
            workflow_definition=workflow_definition,
            activities=activities,
        )

        execution_read.additional_properties = d
        return execution_read

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
