from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.retry_failure_request_input_parameter_overrides_additional_property import (
        RetryFailureRequestInputParameterOverridesAdditionalProperty,
    )


T = TypeVar("T", bound="RetryFailureRequestInputParameterOverrides")


@_attrs_define
class RetryFailureRequestInputParameterOverrides:
    """Input parameter overrides for the retry's starting nodes, keyed by node id then parameter name (SDP AC-14/R10c).
    Each override replaces the value the node would otherwise receive, after upstream outputs are injected, so the
    supplied value is what executes. Parameter names must already exist on that node in the retained workflow version,
    and node ids must be among the retry's starting points; anything else is rejected. Overrides apply to this retry run
    only — the workflow definition is never modified, and a permanent change requires editing, saving, and publishing
    the workflow.

    """

    additional_properties: dict[str, RetryFailureRequestInputParameterOverridesAdditionalProperty] = _attrs_field(
        init=False, factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.retry_failure_request_input_parameter_overrides_additional_property import (
            RetryFailureRequestInputParameterOverridesAdditionalProperty,
        )

        d = dict(src_dict)
        retry_failure_request_input_parameter_overrides = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = RetryFailureRequestInputParameterOverridesAdditionalProperty.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        retry_failure_request_input_parameter_overrides.additional_properties = additional_properties
        return retry_failure_request_input_parameter_overrides

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> RetryFailureRequestInputParameterOverridesAdditionalProperty:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: RetryFailureRequestInputParameterOverridesAdditionalProperty) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
