from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.gap_reason import GapReason
from ..models.initialization_kind import InitializationKind
from ..models.recovery_policy import RecoveryPolicy

T = TypeVar("T", bound="KafkaPartitionInitialPositionRead")


@_attrs_define
class KafkaPartitionInitialPositionRead:
    """Lossless metadata schema for later read/control callers; no route is added.

    Attributes:
        source_id (UUID):
        partition (int):
        initialization_kind (InitializationKind | None):
        initial_next_offset (None | str):
        initialized_at (datetime.datetime | None):
        initial_metadata_missing (bool):
        observed_group_next_offset (None | str):
        initial_commit_confirmed_at (datetime.datetime | None):
        recovery_revision (int):
        recovery_boundary (None | str):
        recovery_confirmed_at (datetime.datetime | None):
        recovery_policy (None | RecoveryPolicy):
        recovery_reason (None | str):
        duplicate_risk_acknowledged (bool):
        gap_detected_at (datetime.datetime | None):
        gap_reason (GapReason | None):
        pending_boundary (None | str):
        pending_policy (None | RecoveryPolicy):
        pending_reason (None | str):
        pending_duplicate_risk_acknowledged (bool):
        superseded_recovery_revision (int | None):
        superseded_recovery_boundary (None | str):
    """

    source_id: UUID
    partition: int
    initialization_kind: InitializationKind | None
    initial_next_offset: None | str
    initialized_at: datetime.datetime | None
    initial_metadata_missing: bool
    observed_group_next_offset: None | str
    initial_commit_confirmed_at: datetime.datetime | None
    recovery_revision: int
    recovery_boundary: None | str
    recovery_confirmed_at: datetime.datetime | None
    recovery_policy: None | RecoveryPolicy
    recovery_reason: None | str
    duplicate_risk_acknowledged: bool
    gap_detected_at: datetime.datetime | None
    gap_reason: GapReason | None
    pending_boundary: None | str
    pending_policy: None | RecoveryPolicy
    pending_reason: None | str
    pending_duplicate_risk_acknowledged: bool
    superseded_recovery_revision: int | None
    superseded_recovery_boundary: None | str

    def to_dict(self) -> dict[str, Any]:
        source_id = str(self.source_id)

        partition = self.partition

        initialization_kind: None | str
        if isinstance(self.initialization_kind, InitializationKind):
            initialization_kind = self.initialization_kind.value
        else:
            initialization_kind = self.initialization_kind

        initial_next_offset: None | str
        initial_next_offset = self.initial_next_offset

        initialized_at: None | str
        if isinstance(self.initialized_at, datetime.datetime):
            initialized_at = self.initialized_at.isoformat()
        else:
            initialized_at = self.initialized_at

        initial_metadata_missing = self.initial_metadata_missing

        observed_group_next_offset: None | str
        observed_group_next_offset = self.observed_group_next_offset

        initial_commit_confirmed_at: None | str
        if isinstance(self.initial_commit_confirmed_at, datetime.datetime):
            initial_commit_confirmed_at = self.initial_commit_confirmed_at.isoformat()
        else:
            initial_commit_confirmed_at = self.initial_commit_confirmed_at

        recovery_revision = self.recovery_revision

        recovery_boundary: None | str
        recovery_boundary = self.recovery_boundary

        recovery_confirmed_at: None | str
        if isinstance(self.recovery_confirmed_at, datetime.datetime):
            recovery_confirmed_at = self.recovery_confirmed_at.isoformat()
        else:
            recovery_confirmed_at = self.recovery_confirmed_at

        recovery_policy: None | str
        if isinstance(self.recovery_policy, RecoveryPolicy):
            recovery_policy = self.recovery_policy.value
        else:
            recovery_policy = self.recovery_policy

        recovery_reason: None | str
        recovery_reason = self.recovery_reason

        duplicate_risk_acknowledged = self.duplicate_risk_acknowledged

        gap_detected_at: None | str
        if isinstance(self.gap_detected_at, datetime.datetime):
            gap_detected_at = self.gap_detected_at.isoformat()
        else:
            gap_detected_at = self.gap_detected_at

        gap_reason: None | str
        if isinstance(self.gap_reason, GapReason):
            gap_reason = self.gap_reason.value
        else:
            gap_reason = self.gap_reason

        pending_boundary: None | str
        pending_boundary = self.pending_boundary

        pending_policy: None | str
        if isinstance(self.pending_policy, RecoveryPolicy):
            pending_policy = self.pending_policy.value
        else:
            pending_policy = self.pending_policy

        pending_reason: None | str
        pending_reason = self.pending_reason

        pending_duplicate_risk_acknowledged = self.pending_duplicate_risk_acknowledged

        superseded_recovery_revision: int | None
        superseded_recovery_revision = self.superseded_recovery_revision

        superseded_recovery_boundary: None | str
        superseded_recovery_boundary = self.superseded_recovery_boundary

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "source_id": source_id,
                "partition": partition,
                "initialization_kind": initialization_kind,
                "initial_next_offset": initial_next_offset,
                "initialized_at": initialized_at,
                "initial_metadata_missing": initial_metadata_missing,
                "observed_group_next_offset": observed_group_next_offset,
                "initial_commit_confirmed_at": initial_commit_confirmed_at,
                "recovery_revision": recovery_revision,
                "recovery_boundary": recovery_boundary,
                "recovery_confirmed_at": recovery_confirmed_at,
                "recovery_policy": recovery_policy,
                "recovery_reason": recovery_reason,
                "duplicate_risk_acknowledged": duplicate_risk_acknowledged,
                "gap_detected_at": gap_detected_at,
                "gap_reason": gap_reason,
                "pending_boundary": pending_boundary,
                "pending_policy": pending_policy,
                "pending_reason": pending_reason,
                "pending_duplicate_risk_acknowledged": pending_duplicate_risk_acknowledged,
                "superseded_recovery_revision": superseded_recovery_revision,
                "superseded_recovery_boundary": superseded_recovery_boundary,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source_id = UUID(d.pop("source_id"))

        partition = d.pop("partition")

        def _parse_initialization_kind(data: object) -> InitializationKind | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                initialization_kind_type_0 = InitializationKind(data)

                return initialization_kind_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(InitializationKind | None, data)

        initialization_kind = _parse_initialization_kind(d.pop("initialization_kind"))

        def _parse_initial_next_offset(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        initial_next_offset = _parse_initial_next_offset(d.pop("initial_next_offset"))

        def _parse_initialized_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                initialized_at_type_0 = isoparse(data)

                return initialized_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        initialized_at = _parse_initialized_at(d.pop("initialized_at"))

        initial_metadata_missing = d.pop("initial_metadata_missing")

        def _parse_observed_group_next_offset(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        observed_group_next_offset = _parse_observed_group_next_offset(d.pop("observed_group_next_offset"))

        def _parse_initial_commit_confirmed_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                initial_commit_confirmed_at_type_0 = isoparse(data)

                return initial_commit_confirmed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        initial_commit_confirmed_at = _parse_initial_commit_confirmed_at(d.pop("initial_commit_confirmed_at"))

        recovery_revision = d.pop("recovery_revision")

        def _parse_recovery_boundary(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        recovery_boundary = _parse_recovery_boundary(d.pop("recovery_boundary"))

        def _parse_recovery_confirmed_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                recovery_confirmed_at_type_0 = isoparse(data)

                return recovery_confirmed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        recovery_confirmed_at = _parse_recovery_confirmed_at(d.pop("recovery_confirmed_at"))

        def _parse_recovery_policy(data: object) -> None | RecoveryPolicy:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                recovery_policy_type_0 = RecoveryPolicy(data)

                return recovery_policy_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecoveryPolicy, data)

        recovery_policy = _parse_recovery_policy(d.pop("recovery_policy"))

        def _parse_recovery_reason(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        recovery_reason = _parse_recovery_reason(d.pop("recovery_reason"))

        duplicate_risk_acknowledged = d.pop("duplicate_risk_acknowledged")

        def _parse_gap_detected_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                gap_detected_at_type_0 = isoparse(data)

                return gap_detected_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        gap_detected_at = _parse_gap_detected_at(d.pop("gap_detected_at"))

        def _parse_gap_reason(data: object) -> GapReason | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                gap_reason_type_0 = GapReason(data)

                return gap_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GapReason | None, data)

        gap_reason = _parse_gap_reason(d.pop("gap_reason"))

        def _parse_pending_boundary(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        pending_boundary = _parse_pending_boundary(d.pop("pending_boundary"))

        def _parse_pending_policy(data: object) -> None | RecoveryPolicy:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pending_policy_type_0 = RecoveryPolicy(data)

                return pending_policy_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecoveryPolicy, data)

        pending_policy = _parse_pending_policy(d.pop("pending_policy"))

        def _parse_pending_reason(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        pending_reason = _parse_pending_reason(d.pop("pending_reason"))

        pending_duplicate_risk_acknowledged = d.pop("pending_duplicate_risk_acknowledged")

        def _parse_superseded_recovery_revision(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        superseded_recovery_revision = _parse_superseded_recovery_revision(d.pop("superseded_recovery_revision"))

        def _parse_superseded_recovery_boundary(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        superseded_recovery_boundary = _parse_superseded_recovery_boundary(d.pop("superseded_recovery_boundary"))

        kafka_partition_initial_position_read = cls(
            source_id=source_id,
            partition=partition,
            initialization_kind=initialization_kind,
            initial_next_offset=initial_next_offset,
            initialized_at=initialized_at,
            initial_metadata_missing=initial_metadata_missing,
            observed_group_next_offset=observed_group_next_offset,
            initial_commit_confirmed_at=initial_commit_confirmed_at,
            recovery_revision=recovery_revision,
            recovery_boundary=recovery_boundary,
            recovery_confirmed_at=recovery_confirmed_at,
            recovery_policy=recovery_policy,
            recovery_reason=recovery_reason,
            duplicate_risk_acknowledged=duplicate_risk_acknowledged,
            gap_detected_at=gap_detected_at,
            gap_reason=gap_reason,
            pending_boundary=pending_boundary,
            pending_policy=pending_policy,
            pending_reason=pending_reason,
            pending_duplicate_risk_acknowledged=pending_duplicate_risk_acknowledged,
            superseded_recovery_revision=superseded_recovery_revision,
            superseded_recovery_boundary=superseded_recovery_boundary,
        )

        return kafka_partition_initial_position_read
