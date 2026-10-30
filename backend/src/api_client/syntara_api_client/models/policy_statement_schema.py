from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.policy_statement_schema_conditions_type_0 import PolicyStatementSchemaConditionsType0


T = TypeVar("T", bound="PolicyStatementSchema")


@_attrs_define
class PolicyStatementSchema:
    """A single policy statement.

    Attributes:
        effect (str): allow or deny; deny requires step_type:write and scope any or project
        actions (list[str]): List of resource_type:action strings
        scope (str): any, self, or project
        conditions (None | PolicyStatementSchemaConditionsType0 | Unset): Optional attribute-based conditions
    """

    effect: str
    actions: list[str]
    scope: str
    conditions: None | PolicyStatementSchemaConditionsType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.policy_statement_schema_conditions_type_0 import PolicyStatementSchemaConditionsType0

        effect = self.effect

        actions = self.actions

        scope = self.scope

        conditions: dict[str, Any] | None | Unset
        if isinstance(self.conditions, Unset):
            conditions = UNSET
        elif isinstance(self.conditions, PolicyStatementSchemaConditionsType0):
            conditions = self.conditions.to_dict()
        else:
            conditions = self.conditions

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "effect": effect,
                "actions": actions,
                "scope": scope,
            }
        )
        if conditions is not UNSET:
            field_dict["conditions"] = conditions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.policy_statement_schema_conditions_type_0 import PolicyStatementSchemaConditionsType0

        d = dict(src_dict)
        effect = d.pop("effect")

        actions = cast(list[str], d.pop("actions"))

        scope = d.pop("scope")

        def _parse_conditions(data: object) -> None | PolicyStatementSchemaConditionsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                conditions_type_0 = PolicyStatementSchemaConditionsType0.from_dict(data)

                return conditions_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PolicyStatementSchemaConditionsType0 | Unset, data)

        conditions = _parse_conditions(d.pop("conditions", UNSET))

        policy_statement_schema = cls(
            effect=effect,
            actions=actions,
            scope=scope,
            conditions=conditions,
        )

        policy_statement_schema.additional_properties = d
        return policy_statement_schema

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
