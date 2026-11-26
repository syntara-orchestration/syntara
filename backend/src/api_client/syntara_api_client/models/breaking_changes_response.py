from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.trigger_breaking_changes import TriggerBreakingChanges
    from ..models.workflow_reference_read import WorkflowReferenceRead


T = TypeVar("T", bound="BreakingChangesResponse")


@_attrs_define
class BreakingChangesResponse:
    """Response containing output contract changes and visible parent references.

    Attributes:
        has_breaking_changes (bool): Whether any detected output contract change is breaking.
        triggers (list[TriggerBreakingChanges]): Per-trigger groups containing breaking changes only; empty when none
            are breaking.
        has_contract_changes (bool | Unset): Whether any output schema or source mapping changed, including nonbreaking
            changes. Default: False.
        contract_changes (list[TriggerBreakingChanges] | Unset): All detected per-trigger changes, including nonbreaking
            changes.
        parent_workflows (list[WorkflowReferenceRead] | Unset): Visible, currently published parent workflow steps
            referencing triggers whose output contracts changed.
    """

    has_breaking_changes: bool
    triggers: list[TriggerBreakingChanges]
    has_contract_changes: bool | Unset = False
    contract_changes: list[TriggerBreakingChanges] | Unset = UNSET
    parent_workflows: list[WorkflowReferenceRead] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        has_breaking_changes = self.has_breaking_changes

        triggers = []
        for triggers_item_data in self.triggers:
            triggers_item = triggers_item_data.to_dict()
            triggers.append(triggers_item)

        has_contract_changes = self.has_contract_changes

        contract_changes: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.contract_changes, Unset):
            contract_changes = []
            for contract_changes_item_data in self.contract_changes:
                contract_changes_item = contract_changes_item_data.to_dict()
                contract_changes.append(contract_changes_item)

        parent_workflows: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.parent_workflows, Unset):
            parent_workflows = []
            for parent_workflows_item_data in self.parent_workflows:
                parent_workflows_item = parent_workflows_item_data.to_dict()
                parent_workflows.append(parent_workflows_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "has_breaking_changes": has_breaking_changes,
                "triggers": triggers,
            }
        )
        if has_contract_changes is not UNSET:
            field_dict["has_contract_changes"] = has_contract_changes
        if contract_changes is not UNSET:
            field_dict["contract_changes"] = contract_changes
        if parent_workflows is not UNSET:
            field_dict["parent_workflows"] = parent_workflows

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.trigger_breaking_changes import TriggerBreakingChanges
        from ..models.workflow_reference_read import WorkflowReferenceRead

        d = dict(src_dict)
        has_breaking_changes = d.pop("has_breaking_changes")

        triggers = []
        _triggers = d.pop("triggers")
        for triggers_item_data in _triggers:
            triggers_item = TriggerBreakingChanges.from_dict(triggers_item_data)

            triggers.append(triggers_item)

        has_contract_changes = d.pop("has_contract_changes", UNSET)

        _contract_changes = d.pop("contract_changes", UNSET)
        contract_changes: list[TriggerBreakingChanges] | Unset = UNSET
        if _contract_changes is not UNSET:
            contract_changes = []
            for contract_changes_item_data in _contract_changes:
                contract_changes_item = TriggerBreakingChanges.from_dict(contract_changes_item_data)

                contract_changes.append(contract_changes_item)

        _parent_workflows = d.pop("parent_workflows", UNSET)
        parent_workflows: list[WorkflowReferenceRead] | Unset = UNSET
        if _parent_workflows is not UNSET:
            parent_workflows = []
            for parent_workflows_item_data in _parent_workflows:
                parent_workflows_item = WorkflowReferenceRead.from_dict(parent_workflows_item_data)

                parent_workflows.append(parent_workflows_item)

        breaking_changes_response = cls(
            has_breaking_changes=has_breaking_changes,
            triggers=triggers,
            has_contract_changes=has_contract_changes,
            contract_changes=contract_changes,
            parent_workflows=parent_workflows,
        )

        return breaking_changes_response
