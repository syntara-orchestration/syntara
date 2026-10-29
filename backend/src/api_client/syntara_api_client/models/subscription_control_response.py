from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.runtime_state import RuntimeState
from ..models.subscription_control_response_convergence import SubscriptionControlResponseConvergence
from ..types import UNSET, Unset

T = TypeVar("T", bound="SubscriptionControlResponse")


@_attrs_define
class SubscriptionControlResponse:
    """A committed action; pending is not proof that every consumer has stopped.

    Attributes:
        subscription_id (UUID):
        source_id (UUID):
        configuration_revision (int):
        source_generation (int):
        convergence (SubscriptionControlResponseConvergence):
        applied_revision (int | None | Unset):
        runtime_state (None | RuntimeState | Unset):
    """

    subscription_id: UUID
    source_id: UUID
    configuration_revision: int
    source_generation: int
    convergence: SubscriptionControlResponseConvergence
    applied_revision: int | None | Unset = UNSET
    runtime_state: None | RuntimeState | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = str(self.subscription_id)

        source_id = str(self.source_id)

        configuration_revision = self.configuration_revision

        source_generation = self.source_generation

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
                "subscription_id": subscription_id,
                "source_id": source_id,
                "configuration_revision": configuration_revision,
                "source_generation": source_generation,
                "convergence": convergence,
            }
        )
        if applied_revision is not UNSET:
            field_dict["applied_revision"] = applied_revision
        if runtime_state is not UNSET:
            field_dict["runtime_state"] = runtime_state

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        subscription_id = UUID(d.pop("subscription_id"))

        source_id = UUID(d.pop("source_id"))

        configuration_revision = d.pop("configuration_revision")

        source_generation = d.pop("source_generation")

        convergence = SubscriptionControlResponseConvergence(d.pop("convergence"))

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

        subscription_control_response = cls(
            subscription_id=subscription_id,
            source_id=source_id,
            configuration_revision=configuration_revision,
            source_generation=source_generation,
            convergence=convergence,
            applied_revision=applied_revision,
            runtime_state=runtime_state,
        )

        subscription_control_response.additional_properties = d
        return subscription_control_response

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
