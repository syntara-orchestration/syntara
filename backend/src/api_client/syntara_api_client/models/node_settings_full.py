from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.retry_policy_parameters import RetryPolicyParameters


T = TypeVar("T", bound="NodeSettingsFull")


@_attrs_define
class NodeSettingsFull:
    """Full settings with retry_policy (http_request, aap_job_template, aap_workflow_job_template).

    Attributes:
        continue_on_failure (bool | None | Unset):
        disabled (bool | None | Unset):
        timeout (int | None | Unset):
        retry_policy (None | RetryPolicyParameters | Unset):
    """

    continue_on_failure: bool | None | Unset = UNSET
    disabled: bool | None | Unset = UNSET
    timeout: int | None | Unset = UNSET
    retry_policy: None | RetryPolicyParameters | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.retry_policy_parameters import RetryPolicyParameters

        continue_on_failure: bool | None | Unset
        if isinstance(self.continue_on_failure, Unset):
            continue_on_failure = UNSET
        else:
            continue_on_failure = self.continue_on_failure

        disabled: bool | None | Unset
        if isinstance(self.disabled, Unset):
            disabled = UNSET
        else:
            disabled = self.disabled

        timeout: int | None | Unset
        if isinstance(self.timeout, Unset):
            timeout = UNSET
        else:
            timeout = self.timeout

        retry_policy: dict[str, Any] | None | Unset
        if isinstance(self.retry_policy, Unset):
            retry_policy = UNSET
        elif isinstance(self.retry_policy, RetryPolicyParameters):
            retry_policy = self.retry_policy.to_dict()
        else:
            retry_policy = self.retry_policy

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if continue_on_failure is not UNSET:
            field_dict["continue_on_failure"] = continue_on_failure
        if disabled is not UNSET:
            field_dict["disabled"] = disabled
        if timeout is not UNSET:
            field_dict["timeout"] = timeout
        if retry_policy is not UNSET:
            field_dict["retry_policy"] = retry_policy

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.retry_policy_parameters import RetryPolicyParameters

        d = dict(src_dict)

        def _parse_continue_on_failure(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        continue_on_failure = _parse_continue_on_failure(d.pop("continue_on_failure", UNSET))

        def _parse_disabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        disabled = _parse_disabled(d.pop("disabled", UNSET))

        def _parse_timeout(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        timeout = _parse_timeout(d.pop("timeout", UNSET))

        def _parse_retry_policy(data: object) -> None | RetryPolicyParameters | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                retry_policy_type_0 = RetryPolicyParameters.from_dict(data)

                return retry_policy_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RetryPolicyParameters | Unset, data)

        retry_policy = _parse_retry_policy(d.pop("retry_policy", UNSET))

        node_settings_full = cls(
            continue_on_failure=continue_on_failure,
            disabled=disabled,
            timeout=timeout,
            retry_policy=retry_policy,
        )

        return node_settings_full
