from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.retry_failure_request_input_parameter_overrides import RetryFailureRequestInputParameterOverrides


T = TypeVar("T", bound="RetryFailureRequest")


@_attrs_define
class RetryFailureRequest:
    """Request body for POST /executions/{id}/retry_from_failure.

    Attributes:
        retry_point_ids (list[str] | Unset): Retry points to resume from (node IDs from the source execution). A subset
            may be passed when multiple parallel branches failed; unselected branches are skipped. Empty selects the
            default: all currently failed nodes. This is what the caller asks for; the points that will actually run come
            back as eligible_point_ids on the response, which can differ.
        input_parameter_overrides (RetryFailureRequestInputParameterOverrides | Unset): Input parameter overrides for
            the retry's starting nodes, keyed by node id then parameter name (SDP AC-14/R10c). Each override replaces the
            value the node would otherwise receive, after upstream outputs are injected, so the supplied value is what
            executes. Parameter names must already exist on that node in the retained workflow version, and node ids must be
            among the retry's starting points; anything else is rejected. Overrides apply to this retry run only — the
            workflow definition is never modified, and a permanent change requires editing, saving, and publishing the
            workflow.
    """

    retry_point_ids: list[str] | Unset = UNSET
    input_parameter_overrides: RetryFailureRequestInputParameterOverrides | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        retry_point_ids: list[str] | Unset = UNSET
        if not isinstance(self.retry_point_ids, Unset):
            retry_point_ids = self.retry_point_ids

        input_parameter_overrides: dict[str, Any] | Unset = UNSET
        if not isinstance(self.input_parameter_overrides, Unset):
            input_parameter_overrides = self.input_parameter_overrides.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if retry_point_ids is not UNSET:
            field_dict["retry_point_ids"] = retry_point_ids
        if input_parameter_overrides is not UNSET:
            field_dict["input_parameter_overrides"] = input_parameter_overrides

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.retry_failure_request_input_parameter_overrides import RetryFailureRequestInputParameterOverrides

        d = dict(src_dict)
        retry_point_ids = cast(list[str], d.pop("retry_point_ids", UNSET))

        _input_parameter_overrides = d.pop("input_parameter_overrides", UNSET)
        input_parameter_overrides: RetryFailureRequestInputParameterOverrides | Unset
        if isinstance(_input_parameter_overrides, Unset):
            input_parameter_overrides = UNSET
        else:
            input_parameter_overrides = RetryFailureRequestInputParameterOverrides.from_dict(_input_parameter_overrides)

        retry_failure_request = cls(
            retry_point_ids=retry_point_ids,
            input_parameter_overrides=input_parameter_overrides,
        )

        retry_failure_request.additional_properties = d
        return retry_failure_request

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
