from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

T = TypeVar("T", bound="IntegrationProjectAssignmentRead")


@_attrs_define
class IntegrationProjectAssignmentRead:
    """Read schema for a single project assignment.

    Attributes:
        project_id (UUID):
        project_name (str):
        created_at (datetime.datetime):
    """

    project_id: UUID
    project_name: str
    created_at: datetime.datetime

    def to_dict(self) -> dict[str, Any]:
        project_id = str(self.project_id)

        project_name = self.project_name

        created_at = self.created_at.isoformat()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "project_id": project_id,
                "project_name": project_name,
                "created_at": created_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        project_id = UUID(d.pop("project_id"))

        project_name = d.pop("project_name")

        created_at = isoparse(d.pop("created_at"))

        integration_project_assignment_read = cls(
            project_id=project_id,
            project_name=project_name,
            created_at=created_at,
        )

        return integration_project_assignment_read
