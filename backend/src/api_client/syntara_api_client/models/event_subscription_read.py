from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.event_subscription_read_convergence import EventSubscriptionReadConvergence
from ..models.runtime_state import RuntimeState
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.event_subscription_read_input_schema_type_0 import EventSubscriptionReadInputSchemaType0
    from ..models.event_subscription_recovery_read import EventSubscriptionRecoveryRead
    from ..models.event_subscription_source_read import EventSubscriptionSourceRead
    from ..models.kafka_partition_initial_position_read import KafkaPartitionInitialPositionRead


T = TypeVar("T", bound="EventSubscriptionRead")


@_attrs_define
class EventSubscriptionRead:
    """Published configuration, recovery evidence and acknowledged runtime convergence.

    Attributes:
        id (UUID):
        workflow_id (UUID):
        project_id (UUID):
        trigger_node_id (str):
        published_version_id (UUID):
        configuration_revision (int):
        runtime_credential_id (None | UUID):
        input_schema (EventSubscriptionReadInputSchemaType0 | None):
        desired_enabled (bool):
        paused (bool):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        source (EventSubscriptionSourceRead): The current source's non-secret configuration.
        retired (bool | Unset):  Default: False.
        sources (list[EventSubscriptionSourceRead] | Unset):
        initialization (list[KafkaPartitionInitialPositionRead] | Unset):
        recovery (list[EventSubscriptionRecoveryRead] | Unset):
        convergence (EventSubscriptionReadConvergence | Unset):  Default: EventSubscriptionReadConvergence.PENDING.
        applied_revision (int | None | Unset):
        runtime_state (None | RuntimeState | Unset):
    """

    id: UUID
    workflow_id: UUID
    project_id: UUID
    trigger_node_id: str
    published_version_id: UUID
    configuration_revision: int
    runtime_credential_id: None | UUID
    input_schema: EventSubscriptionReadInputSchemaType0 | None
    desired_enabled: bool
    paused: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    source: EventSubscriptionSourceRead
    retired: bool | Unset = False
    sources: list[EventSubscriptionSourceRead] | Unset = UNSET
    initialization: list[KafkaPartitionInitialPositionRead] | Unset = UNSET
    recovery: list[EventSubscriptionRecoveryRead] | Unset = UNSET
    convergence: EventSubscriptionReadConvergence | Unset = EventSubscriptionReadConvergence.PENDING
    applied_revision: int | None | Unset = UNSET
    runtime_state: None | RuntimeState | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.event_subscription_read_input_schema_type_0 import EventSubscriptionReadInputSchemaType0

        id = str(self.id)

        workflow_id = str(self.workflow_id)

        project_id = str(self.project_id)

        trigger_node_id = self.trigger_node_id

        published_version_id = str(self.published_version_id)

        configuration_revision = self.configuration_revision

        runtime_credential_id: None | str
        if isinstance(self.runtime_credential_id, UUID):
            runtime_credential_id = str(self.runtime_credential_id)
        else:
            runtime_credential_id = self.runtime_credential_id

        input_schema: dict[str, Any] | None
        if isinstance(self.input_schema, EventSubscriptionReadInputSchemaType0):
            input_schema = self.input_schema.to_dict()
        else:
            input_schema = self.input_schema

        desired_enabled = self.desired_enabled

        paused = self.paused

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        source = self.source.to_dict()

        retired = self.retired

        sources: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.sources, Unset):
            sources = []
            for sources_item_data in self.sources:
                sources_item = sources_item_data.to_dict()
                sources.append(sources_item)

        initialization: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.initialization, Unset):
            initialization = []
            for initialization_item_data in self.initialization:
                initialization_item = initialization_item_data.to_dict()
                initialization.append(initialization_item)

        recovery: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.recovery, Unset):
            recovery = []
            for recovery_item_data in self.recovery:
                recovery_item = recovery_item_data.to_dict()
                recovery.append(recovery_item)

        convergence: str | Unset = UNSET
        if not isinstance(self.convergence, Unset):
            convergence = self.convergence.value

        applied_revision: int | None | Unset
        if isinstance(self.applied_revision, Unset):
            applied_revision = UNSET
        else:
            applied_revision = self.applied_revision

        runtime_state: None | str | Unset
        if isinstance(self.runtime_state, Unset):
            runtime_state = UNSET
        elif isinstance(self.runtime_state, RuntimeState):
            runtime_state = self.runtime_state.value
        else:
            runtime_state = self.runtime_state

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workflow_id": workflow_id,
                "project_id": project_id,
                "trigger_node_id": trigger_node_id,
                "published_version_id": published_version_id,
                "configuration_revision": configuration_revision,
                "runtime_credential_id": runtime_credential_id,
                "input_schema": input_schema,
                "desired_enabled": desired_enabled,
                "paused": paused,
                "created_at": created_at,
                "updated_at": updated_at,
                "source": source,
            }
        )
        if retired is not UNSET:
            field_dict["retired"] = retired
        if sources is not UNSET:
            field_dict["sources"] = sources
        if initialization is not UNSET:
            field_dict["initialization"] = initialization
        if recovery is not UNSET:
            field_dict["recovery"] = recovery
        if convergence is not UNSET:
            field_dict["convergence"] = convergence
        if applied_revision is not UNSET:
            field_dict["applied_revision"] = applied_revision
        if runtime_state is not UNSET:
            field_dict["runtime_state"] = runtime_state

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.event_subscription_read_input_schema_type_0 import EventSubscriptionReadInputSchemaType0
        from ..models.event_subscription_recovery_read import EventSubscriptionRecoveryRead
        from ..models.event_subscription_source_read import EventSubscriptionSourceRead
        from ..models.kafka_partition_initial_position_read import KafkaPartitionInitialPositionRead

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        workflow_id = UUID(d.pop("workflow_id"))

        project_id = UUID(d.pop("project_id"))

        trigger_node_id = d.pop("trigger_node_id")

        published_version_id = UUID(d.pop("published_version_id"))

        configuration_revision = d.pop("configuration_revision")

        def _parse_runtime_credential_id(data: object) -> None | UUID:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                runtime_credential_id_type_0 = UUID(data)

                return runtime_credential_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UUID, data)

        runtime_credential_id = _parse_runtime_credential_id(d.pop("runtime_credential_id"))

        def _parse_input_schema(data: object) -> EventSubscriptionReadInputSchemaType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_schema_type_0 = EventSubscriptionReadInputSchemaType0.from_dict(data)

                return input_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(EventSubscriptionReadInputSchemaType0 | None, data)

        input_schema = _parse_input_schema(d.pop("input_schema"))

        desired_enabled = d.pop("desired_enabled")

        paused = d.pop("paused")

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        source = EventSubscriptionSourceRead.from_dict(d.pop("source"))

        retired = d.pop("retired", UNSET)

        _sources = d.pop("sources", UNSET)
        sources: list[EventSubscriptionSourceRead] | Unset = UNSET
        if _sources is not UNSET:
            sources = []
            for sources_item_data in _sources:
                sources_item = EventSubscriptionSourceRead.from_dict(sources_item_data)

                sources.append(sources_item)

        _initialization = d.pop("initialization", UNSET)
        initialization: list[KafkaPartitionInitialPositionRead] | Unset = UNSET
        if _initialization is not UNSET:
            initialization = []
            for initialization_item_data in _initialization:
                initialization_item = KafkaPartitionInitialPositionRead.from_dict(initialization_item_data)

                initialization.append(initialization_item)

        _recovery = d.pop("recovery", UNSET)
        recovery: list[EventSubscriptionRecoveryRead] | Unset = UNSET
        if _recovery is not UNSET:
            recovery = []
            for recovery_item_data in _recovery:
                recovery_item = EventSubscriptionRecoveryRead.from_dict(recovery_item_data)

                recovery.append(recovery_item)

        _convergence = d.pop("convergence", UNSET)
        convergence: EventSubscriptionReadConvergence | Unset
        if isinstance(_convergence, Unset):
            convergence = UNSET
        else:
            convergence = EventSubscriptionReadConvergence(_convergence)

        def _parse_applied_revision(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        applied_revision = _parse_applied_revision(d.pop("applied_revision", UNSET))

        def _parse_runtime_state(data: object) -> None | RuntimeState | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                runtime_state_type_0 = RuntimeState(data)

                return runtime_state_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RuntimeState | Unset, data)

        runtime_state = _parse_runtime_state(d.pop("runtime_state", UNSET))

        event_subscription_read = cls(
            id=id,
            workflow_id=workflow_id,
            project_id=project_id,
            trigger_node_id=trigger_node_id,
            published_version_id=published_version_id,
            configuration_revision=configuration_revision,
            runtime_credential_id=runtime_credential_id,
            input_schema=input_schema,
            desired_enabled=desired_enabled,
            paused=paused,
            created_at=created_at,
            updated_at=updated_at,
            source=source,
            retired=retired,
            sources=sources,
            initialization=initialization,
            recovery=recovery,
            convergence=convergence,
            applied_revision=applied_revision,
            runtime_state=runtime_state,
        )

        event_subscription_read.additional_properties = d
        return event_subscription_read

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
