from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.resource_actions_response_resource_actions import ResourceActionsResponseResourceActions


T = TypeVar("T", bound="ResourceActionsResponse")


@_attrs_define
class ResourceActionsResponse:
    """Available resource types and their valid actions.

    Attributes:
        resource_actions (ResourceActionsResponseResourceActions): Map of resource types to their valid actions
    """

    resource_actions: ResourceActionsResponseResourceActions

    def to_dict(self) -> dict[str, Any]:
        resource_actions = self.resource_actions.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "resource_actions": resource_actions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.resource_actions_response_resource_actions import ResourceActionsResponseResourceActions

        d = dict(src_dict)
        resource_actions = ResourceActionsResponseResourceActions.from_dict(d.pop("resource_actions"))

        resource_actions_response = cls(
            resource_actions=resource_actions,
        )

        return resource_actions_response
