from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workflow_invocation_trigger_schema import WorkflowInvocationTriggerSchema


T = TypeVar("T", bound="WorkflowInvocationSchemaRead")


@_attrs_define
class WorkflowInvocationSchemaRead:
    """Published invocation schemas for a child workflow.

    Attributes:
        workflow_id (UUID):
        published_version_id (UUID):
        published_version (int):
        is_eligible (bool):
        triggers (list[WorkflowInvocationTriggerSchema]):
        published_version_name (None | str | Unset):
        published_version_created_at (datetime.datetime | None | Unset):
    """

    workflow_id: UUID
    published_version_id: UUID
    published_version: int
    is_eligible: bool
    triggers: list[WorkflowInvocationTriggerSchema]
    published_version_name: None | str | Unset = UNSET
    published_version_created_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        workflow_id = str(self.workflow_id)

        published_version_id = str(self.published_version_id)

        published_version = self.published_version

        is_eligible = self.is_eligible

        triggers = []
        for triggers_item_data in self.triggers:
            triggers_item = triggers_item_data.to_dict()
            triggers.append(triggers_item)

        published_version_name: None | str | Unset
        if isinstance(self.published_version_name, Unset):
            published_version_name = UNSET
        else:
            published_version_name = self.published_version_name

        published_version_created_at: None | str | Unset
        if isinstance(self.published_version_created_at, Unset):
            published_version_created_at = UNSET
        elif isinstance(self.published_version_created_at, datetime.datetime):
            published_version_created_at = self.published_version_created_at.isoformat()
        else:
            published_version_created_at = self.published_version_created_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "workflow_id": workflow_id,
                "published_version_id": published_version_id,
                "published_version": published_version,
                "is_eligible": is_eligible,
                "triggers": triggers,
            }
        )
        if published_version_name is not UNSET:
            field_dict["published_version_name"] = published_version_name
        if published_version_created_at is not UNSET:
            field_dict["published_version_created_at"] = published_version_created_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workflow_invocation_trigger_schema import WorkflowInvocationTriggerSchema

        d = dict(src_dict)
        workflow_id = UUID(d.pop("workflow_id"))

        published_version_id = UUID(d.pop("published_version_id"))

        published_version = d.pop("published_version")

        is_eligible = d.pop("is_eligible")

        triggers = []
        _triggers = d.pop("triggers")
        for triggers_item_data in _triggers:
            triggers_item = WorkflowInvocationTriggerSchema.from_dict(triggers_item_data)

            triggers.append(triggers_item)

        def _parse_published_version_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        published_version_name = _parse_published_version_name(d.pop("published_version_name", UNSET))

        def _parse_published_version_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                published_version_created_at_type_0 = isoparse(data)

                return published_version_created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        published_version_created_at = _parse_published_version_created_at(d.pop("published_version_created_at", UNSET))

        workflow_invocation_schema_read = cls(
            workflow_id=workflow_id,
            published_version_id=published_version_id,
            published_version=published_version,
            is_eligible=is_eligible,
            triggers=triggers,
            published_version_name=published_version_name,
            published_version_created_at=published_version_created_at,
        )

        workflow_invocation_schema_read.additional_properties = d
        return workflow_invocation_schema_read

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
