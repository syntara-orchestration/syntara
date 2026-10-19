from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.retry_from_failure_validation_response_sanitized_replacements import (
        RetryFromFailureValidationResponseSanitizedReplacements,
    )
    from ..models.retry_from_failure_validation_response_step_count_by_eligible_point import (
        RetryFromFailureValidationResponseStepCountByEligiblePoint,
    )


T = TypeVar("T", bound="RetryFromFailureValidationResponse")


@_attrs_define
class RetryFromFailureValidationResponse:
    """Retry preview (GET /executions/{id}/retry_from_failure_preview).

    Attributes:
        eligible (bool): Whether the retry is allowed to proceed
        reason (None | str | Unset): Rejection reason when eligible is false, null otherwise
        eligible_point_ids (list[str] | Unset): The retry points that will actually run, after cleanup (trimmed,
            deduped, sorted). Equal to the requested retry_point_ids except where sanitized nodes are auto-included and
            superseded failed points are dropped, so it is not always a verbatim echo of the request. On a rejection it
            reports the pre-expansion selection that was assessed.
        sanitized_node_ids (list[str] | Unset): Upstream nodes with sanitized stored outputs referenced on the retry
            path. Populated when the verdict rejects; empty on eligible verdicts (see auto_included_node_ids).
        auto_included_node_ids (list[str] | Unset): Sanitized nodes added as retry points on the default path. Empty on
            explicit selections, which reject instead.
        sanitized_replacements (RetryFromFailureValidationResponseSanitizedReplacements | Unset): For each currently-
            failed node, the sanitized nodes it must be replaced by, if any.
        step_count_by_eligible_point (RetryFromFailureValidationResponseStepCountByEligiblePoint | Unset): Re-run step
            count for each eligible retry point.
        total_step_count (int | Unset): Deduplicated total of steps that will re-run across the eligible points.
            Default: 0.
    """

    eligible: bool
    reason: None | str | Unset = UNSET
    eligible_point_ids: list[str] | Unset = UNSET
    sanitized_node_ids: list[str] | Unset = UNSET
    auto_included_node_ids: list[str] | Unset = UNSET
    sanitized_replacements: RetryFromFailureValidationResponseSanitizedReplacements | Unset = UNSET
    step_count_by_eligible_point: RetryFromFailureValidationResponseStepCountByEligiblePoint | Unset = UNSET
    total_step_count: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eligible = self.eligible

        reason: None | str | Unset
        if isinstance(self.reason, Unset):
            reason = UNSET
        else:
            reason = self.reason

        eligible_point_ids: list[str] | Unset = UNSET
        if not isinstance(self.eligible_point_ids, Unset):
            eligible_point_ids = self.eligible_point_ids

        sanitized_node_ids: list[str] | Unset = UNSET
        if not isinstance(self.sanitized_node_ids, Unset):
            sanitized_node_ids = self.sanitized_node_ids

        auto_included_node_ids: list[str] | Unset = UNSET
        if not isinstance(self.auto_included_node_ids, Unset):
            auto_included_node_ids = self.auto_included_node_ids

        sanitized_replacements: dict[str, Any] | Unset = UNSET
        if not isinstance(self.sanitized_replacements, Unset):
            sanitized_replacements = self.sanitized_replacements.to_dict()

        step_count_by_eligible_point: dict[str, Any] | Unset = UNSET
        if not isinstance(self.step_count_by_eligible_point, Unset):
            step_count_by_eligible_point = self.step_count_by_eligible_point.to_dict()

        total_step_count = self.total_step_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "eligible": eligible,
            }
        )
        if reason is not UNSET:
            field_dict["reason"] = reason
        if eligible_point_ids is not UNSET:
            field_dict["eligible_point_ids"] = eligible_point_ids
        if sanitized_node_ids is not UNSET:
            field_dict["sanitized_node_ids"] = sanitized_node_ids
        if auto_included_node_ids is not UNSET:
            field_dict["auto_included_node_ids"] = auto_included_node_ids
        if sanitized_replacements is not UNSET:
            field_dict["sanitized_replacements"] = sanitized_replacements
        if step_count_by_eligible_point is not UNSET:
            field_dict["step_count_by_eligible_point"] = step_count_by_eligible_point
        if total_step_count is not UNSET:
            field_dict["total_step_count"] = total_step_count

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.retry_from_failure_validation_response_sanitized_replacements import (
            RetryFromFailureValidationResponseSanitizedReplacements,
        )
        from ..models.retry_from_failure_validation_response_step_count_by_eligible_point import (
            RetryFromFailureValidationResponseStepCountByEligiblePoint,
        )

        d = dict(src_dict)
        eligible = d.pop("eligible")

        def _parse_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reason = _parse_reason(d.pop("reason", UNSET))

        eligible_point_ids = cast(list[str], d.pop("eligible_point_ids", UNSET))

        sanitized_node_ids = cast(list[str], d.pop("sanitized_node_ids", UNSET))

        auto_included_node_ids = cast(list[str], d.pop("auto_included_node_ids", UNSET))

        _sanitized_replacements = d.pop("sanitized_replacements", UNSET)
        sanitized_replacements: RetryFromFailureValidationResponseSanitizedReplacements | Unset
        if isinstance(_sanitized_replacements, Unset):
            sanitized_replacements = UNSET
        else:
            sanitized_replacements = RetryFromFailureValidationResponseSanitizedReplacements.from_dict(
                _sanitized_replacements
            )

        _step_count_by_eligible_point = d.pop("step_count_by_eligible_point", UNSET)
        step_count_by_eligible_point: RetryFromFailureValidationResponseStepCountByEligiblePoint | Unset
        if isinstance(_step_count_by_eligible_point, Unset):
            step_count_by_eligible_point = UNSET
        else:
            step_count_by_eligible_point = RetryFromFailureValidationResponseStepCountByEligiblePoint.from_dict(
                _step_count_by_eligible_point
            )

        total_step_count = d.pop("total_step_count", UNSET)

        retry_from_failure_validation_response = cls(
            eligible=eligible,
            reason=reason,
            eligible_point_ids=eligible_point_ids,
            sanitized_node_ids=sanitized_node_ids,
            auto_included_node_ids=auto_included_node_ids,
            sanitized_replacements=sanitized_replacements,
            step_count_by_eligible_point=step_count_by_eligible_point,
            total_step_count=total_step_count,
        )

        retry_from_failure_validation_response.additional_properties = d
        return retry_from_failure_validation_response

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
