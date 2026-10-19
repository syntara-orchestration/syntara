"""PostgreSQL delivery repository; all results require the caller's transaction commit.

Use a fresh injected session per task and a short transaction around each call.
Acquisition and freeze share one preparation transaction. No method performs
Temporal, Kafka or Redis I/O, or commits on behalf of an admission caller.
"""

import re
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, or_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.constants import EventDeliveryDefaults, FieldLimits
from syntara.core.models.principal import service_principal_id
from syntara.eventstreams.adapters.record_identity import record_matches_source
from syntara.eventstreams.core.deduplication import (
    ClaimBusy,
    ClaimLost,
    DeliveryCapacityCheck,
    DeliveryClaim,
    DeliveryExpectation,
    DeliveryIdentity,
    DeliveryState,
    FrozenDeliveryBinding,
    RevisionChanged,
    StorageBackpressure,
    TemporalAcceptance,
    TerminalDelivery,
    input_fingerprint,
)
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.delivery_capacity_service import PostgreSQLDeliveryCapacityCheck
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.workflows.models.execution import Execution, ExecutionStatus

_METADATA_KEY = "event_delivery"


class _ClaimExpiredError(Exception):
    """Roll back nested Execution preparation if its claim expires during the write."""


class EventDeliveryStore:
    """Implement token fencing against PostgreSQL state, never against a cached claim."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        capacity_check: DeliveryCapacityCheck | None = None,
        execution_principal_id: UUID | None = None,
    ) -> None:
        """Inject the caller's session and optional test-isolated capacity/principal ports."""
        self.session = session
        self.capacity_check = capacity_check if capacity_check is not None else PostgreSQLDeliveryCapacityCheck(session)
        self.execution_principal_id = (
            execution_principal_id
            if execution_principal_id is not None
            else service_principal_id(get_settings().service_identity)
        )

    async def _now(self) -> datetime:
        return cast("datetime", (await self.session.exec(select(func.clock_timestamp()))).one())

    @staticmethod
    def _validate_worker(owner_worker_id: str) -> None:
        if not isinstance(owner_worker_id, str) or not 1 <= len(owner_worker_id) <= FieldLimits.NAME_MAX_LENGTH:
            msg = "A bounded worker identifier is required"
            raise ValueError(msg)

    @staticmethod
    def _matches_scope(
        identity: DeliveryIdentity, subscription: EventSubscription, source: EventSubscriptionSource
    ) -> bool:
        return (
            subscription.id == identity.subscription_id
            and subscription.workflow_id == identity.workflow_id
            and source.id == identity.source_id
            and source.subscription_id == identity.subscription_id
            and source.generation == identity.source_generation
            and source.deployment_id == identity.deployment_id
            and source.integration_identity == identity.integration_identity
            and source.transport == identity.record.transport
            and record_matches_source(identity.record, source.configuration)
        )

    @staticmethod
    def _admission_current(
        subscription: EventSubscription, source: EventSubscriptionSource, expected: DeliveryExpectation
    ) -> bool:
        return (
            subscription.desired_enabled
            and not subscription.paused
            and not subscription.retired
            and source.retired_at is None
            and subscription.active_source_generation == source.generation
            and subscription.configuration_revision == expected.configuration_revision
            and subscription.published_version_id == expected.published_version_id
        )

    async def _delivery(self, identity: DeliveryIdentity, *, skip_locked: bool = False) -> EventDelivery | None:
        row = (
            await self.session.exec(
                select(EventDelivery)
                .where(col(EventDelivery.identity_digest) == identity.digest)
                .with_for_update(skip_locked=skip_locked)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is not None and row.delivery_identity() != identity:
            msg = "Delivery digest conflicts with retained canonical identity"
            raise ValueError(msg)
        return row

    async def _locked(self, identity: DeliveryIdentity) -> EventDelivery | None:
        lifecycle = await lock_source_lifecycle(self.session, identity.source_id)
        if lifecycle is None or not self._matches_scope(identity, *lifecycle):
            return None
        return await self._delivery(identity)

    async def _current(self, claim: DeliveryClaim) -> EventDelivery | None:
        row = await self._locked(claim.identity)
        if (
            row is None
            or row.state != DeliveryState.IN_PROGRESS
            or row.claim_token != claim.token
            or row.owner_worker_id != claim.owner_worker_id
            or row.lease_until is None
            or row.lease_until <= await self._now()
        ):
            return None
        return row

    @staticmethod
    def _claim(row: EventDelivery) -> DeliveryClaim:
        if row.claim_token is None or row.owner_worker_id is None or row.lease_until is None:
            msg = "Delivery has no processing claim"
            raise ValueError(msg)
        return DeliveryClaim(
            identity=row.delivery_identity(),
            token=row.claim_token,
            owner_worker_id=row.owner_worker_id,
            lease_until=row.lease_until,
            binding=row.frozen_binding,
            attempt_count=row.attempt_count,
            first_start_attempt_at=row.first_start_attempt_at,
            temporal_run_id=row.temporal_run_id,
        )

    @staticmethod
    def _terminal(row: EventDelivery) -> TerminalDelivery:
        if row.resolved_at is None:
            msg = "Delivery is unresolved"
            raise ValueError(msg)
        return TerminalDelivery(
            identity=row.delivery_identity(),
            state=DeliveryState(row.state),
            resolved_at=row.resolved_at,
            execution_id=row.execution_identity if row.frozen_binding is not None else None,
            temporal_run_id=row.temporal_run_id,
            execution_confirmed_at=row.execution_confirmed_at,
        )

    @classmethod
    def _prepared_claim(cls, row: EventDelivery | None) -> DeliveryClaim:
        """Abort the preparation savepoint when its conditional write loses ownership."""
        if row is None:
            raise _ClaimExpiredError
        return cls._claim(row)

    async def _change(self, claim: DeliveryClaim, **values: object) -> EventDelivery | None:
        result = await self.session.execute(
            update(EventDelivery)
            .where(
                col(EventDelivery.identity_digest) == claim.identity.digest,
                col(EventDelivery.state) == DeliveryState.IN_PROGRESS.value,
                col(EventDelivery.claim_token) == claim.token,
                col(EventDelivery.owner_worker_id) == claim.owner_worker_id,
                col(EventDelivery.lease_until) > func.clock_timestamp(),
            )
            .values(**values)
            .returning(EventDelivery)
            .execution_options(populate_existing=True, synchronize_session="fetch")
        )
        return cast("EventDelivery | None", result.scalar_one_or_none())

    async def _takeover(self, row: EventDelivery, owner_worker_id: str) -> DeliveryClaim | ClaimBusy:
        result = await self.session.execute(
            update(EventDelivery)
            .where(
                col(EventDelivery.identity_digest) == row.identity_digest,
                col(EventDelivery.state) == DeliveryState.IN_PROGRESS.value,
                col(EventDelivery.claim_token) == row.claim_token,
                or_(col(EventDelivery.lease_until).is_(None), col(EventDelivery.lease_until) <= func.clock_timestamp()),
                col(EventDelivery.next_attempt_at) <= func.clock_timestamp(),
            )
            .values(
                claim_token=uuid4(),
                owner_worker_id=owner_worker_id,
                lease_until=func.clock_timestamp() + timedelta(seconds=EventDeliveryDefaults.CLAIM_LEASE_SECONDS),
            )
            .returning(EventDelivery)
            .execution_options(populate_existing=True, synchronize_session="fetch")
        )
        changed = cast("EventDelivery | None", result.scalar_one_or_none())
        if changed is None:
            return ClaimBusy(lease_until=max(row.lease_until or row.next_attempt_at, row.next_attempt_at))
        return self._claim(changed)

    async def acquire(
        self, identity: DeliveryIdentity, expected: DeliveryExpectation, owner_worker_id: str
    ) -> DeliveryClaim | ClaimBusy | TerminalDelivery | RevisionChanged | StorageBackpressure:
        """Acquire new work or an expired token, preserving terminal and frozen evidence."""
        self._validate_worker(owner_worker_id)
        lifecycle = await lock_source_lifecycle(self.session, identity.source_id)
        if lifecycle is None or not self._matches_scope(identity, *lifecycle):
            return RevisionChanged()
        row = await self._delivery(identity)
        if row is not None:
            if row.state != DeliveryState.IN_PROGRESS:
                return self._terminal(row)
            return await self._takeover(row, owner_worker_id)
        if not self._admission_current(*lifecycle, expected):
            return RevisionChanged()
        try:
            permitted = await self.capacity_check.permits_new_delivery()
        except (SQLAlchemyError, OSError, TimeoutError):
            permitted = False
        if not permitted:
            return StorageBackpressure()
        await self.session.execute(
            insert(EventDelivery)
            .values(
                **identity.model_dump(exclude={"record"}),
                identity_digest=identity.digest,
                transport=identity.record.transport,
                record_identity=identity.record,
                state=DeliveryState.IN_PROGRESS.value,
                execution_identity=identity.execution_id,
                temporal_workflow_id=identity.temporal_workflow_id,
                claim_token=None,
                owner_worker_id=None,
                lease_until=None,
                next_attempt_at=func.clock_timestamp(),
                created_at=func.clock_timestamp(),
            )
            .on_conflict_do_nothing(index_elements=["identity_digest"])
        )
        row = await self._delivery(identity)
        if row is None:
            msg = "Inserted delivery cannot be read"
            raise RuntimeError(msg)
        return (
            self._terminal(row)
            if row.state != DeliveryState.IN_PROGRESS
            else await self._takeover(row, owner_worker_id)
        )

    async def renew(self, claim: DeliveryClaim) -> DeliveryClaim | ClaimLost:
        """Extend a live current token; an expired token must use takeover."""
        if await self._current(claim) is None:
            return ClaimLost()
        changed = await self._change(
            claim, lease_until=func.clock_timestamp() + timedelta(seconds=EventDeliveryDefaults.CLAIM_LEASE_SECONDS)
        )
        return ClaimLost() if changed is None else self._claim(changed)

    @staticmethod
    def _fingerprint(execution: Execution) -> str:
        context = {key: value for key, value in (execution.execution_metadata or {}).items() if key != _METADATA_KEY}
        return input_fingerprint(execution.input_data, context)

    def _validate_execution(
        self, identity: DeliveryIdentity, binding: FrozenDeliveryBinding, execution: Execution
    ) -> None:
        if (
            execution.id != identity.execution_id
            or execution.workflow_id != identity.workflow_id
            or execution.workflow_version_id != binding.workflow_version_id
            or execution.temporal_workflow_id != identity.temporal_workflow_id
            or execution.created_by != binding.execution_principal_id
            or self._fingerprint(execution) != binding.input_fingerprint
        ):
            msg = "Execution does not match its frozen delivery binding"
            raise ValueError(msg)

    async def freeze(
        self, claim: DeliveryClaim, binding: FrozenDeliveryBinding, execution: Execution
    ) -> DeliveryClaim | ClaimLost | RevisionChanged:
        """Persist a supplied pending Execution with its binding in the claim transaction.

        Pass a newly constructed Execution without first adding it to the session.
        The admission caller must commit acquisition and freeze together.
        """
        row = await self._current(claim)
        if row is None:
            return ClaimLost()
        if row.frozen_binding is not None:
            if row.frozen_binding != binding:
                msg = "A frozen delivery binding cannot be replaced"
                raise ValueError(msg)
            changed = await self._change(claim, frozen_binding=row.frozen_binding)
            return ClaimLost() if changed is None else self._claim(changed)
        subscription = await self.session.get(EventSubscription, claim.identity.subscription_id)
        source = await self.session.get(EventSubscriptionSource, claim.identity.source_id)
        expected = DeliveryExpectation(
            published_version_id=binding.workflow_version_id, configuration_revision=binding.configuration_revision
        )
        if (
            subscription is None
            or source is None
            or not self._admission_current(subscription, source, expected)
            or binding.runtime_credential_id != subscription.runtime_credential_id
            or binding.enabled_by != subscription.enabled_by
            or execution.project_id != subscription.project_id
            or execution.trigger_node_id != subscription.trigger_node_id
        ):
            return RevisionChanged()
        if binding.execution_principal_id != self.execution_principal_id:
            msg = "New delivery preparation requires the configured platform principal"
            raise ValueError(msg)
        self._validate_execution(claim.identity, binding, execution)
        try:
            async with self.session.begin_nested():
                existing = await self.session.get(Execution, claim.identity.execution_id, populate_existing=True)
                prepared = execution if existing is None else existing
                self._validate_execution(claim.identity, binding, prepared)
                if prepared.status != ExecutionStatus.PENDING:
                    msg = "New delivery preparation requires a pending Execution"
                    raise ValueError(msg)
                prepared.execution_metadata = {
                    **(prepared.execution_metadata or {}),
                    _METADATA_KEY: {
                        "identity_digest": claim.identity.digest,
                        "scheduling_state": "prepared",
                        "input_fingerprint": binding.input_fingerprint,
                        "temporal_workflow_id": claim.identity.temporal_workflow_id,
                    },
                }
                self.session.add(prepared)
                await self.session.flush()
                changed = await self._change(claim, frozen_binding=binding, execution_id=prepared.id)
                return self._prepared_claim(changed)
        except _ClaimExpiredError:
            return ClaimLost()

    async def record_start_attempt(self, claim: DeliveryClaim) -> DeliveryClaim | ClaimLost:
        """Fence and persist first attempt/counter before a Temporal RPC is permitted."""
        row = await self._current(claim)
        if row is None:
            return ClaimLost()
        if row.frozen_binding is None or row.execution_id is None:
            msg = "A start attempt requires frozen Execution preparation"
            raise ValueError(msg)
        changed = await self._change(
            claim,
            attempt_count=col(EventDelivery.attempt_count) + 1,
            first_start_attempt_at=func.coalesce(EventDelivery.first_start_attempt_at, func.clock_timestamp()),
        )
        return ClaimLost() if changed is None else self._claim(changed)

    @staticmethod
    def _validate_acceptance(row: EventDelivery, acceptance: TemporalAcceptance) -> None:
        if (
            row.frozen_binding is None
            or row.attempt_count == 0
            or acceptance.execution_id != row.execution_identity
            or acceptance.temporal_workflow_id != row.temporal_workflow_id
            or acceptance.input_fingerprint != row.frozen_binding.input_fingerprint
            or (row.temporal_run_id is not None and row.temporal_run_id != acceptance.temporal_run_id)
        ):
            msg = "Acceptance does not match frozen identity and start-attempt evidence"
            raise ValueError(msg)

    async def record_acceptance(
        self, claim: DeliveryClaim, acceptance: TemporalAcceptance
    ) -> DeliveryClaim | ClaimLost:
        """Retain verified run evidence without declaring scheduling resolved."""
        row = await self._current(claim)
        if row is None:
            return ClaimLost()
        self._validate_acceptance(row, acceptance)
        changed = await self._change(claim, temporal_run_id=acceptance.temporal_run_id)
        return ClaimLost() if changed is None else self._claim(changed)

    async def finalize_scheduled(
        self, claim: DeliveryClaim, acceptance: TemporalAcceptance
    ) -> TerminalDelivery | ClaimLost:
        """Atomically record verified scheduling without changing a newer Execution status."""
        row = await self._locked(claim.identity)
        if row is None or row.claim_token != claim.token or row.owner_worker_id != claim.owner_worker_id:
            return ClaimLost()
        self._validate_acceptance(row, acceptance)
        if row.state == DeliveryState.SCHEDULED:
            return self._terminal(row)
        execution = (
            await self.session.exec(
                select(Execution)
                .where(col(Execution.id) == row.execution_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if execution is None or row.frozen_binding is None:
            msg = "Prepared Execution evidence is unavailable"
            raise ValueError(msg)
        self._validate_execution(claim.identity, row.frozen_binding, execution)
        changed = await self._change(
            claim,
            state=DeliveryState.SCHEDULED.value,
            temporal_run_id=acceptance.temporal_run_id,
            execution_confirmed_at=func.clock_timestamp(),
            resolved_at=func.clock_timestamp(),
        )
        if changed is None:
            return ClaimLost()
        execution.execution_metadata = {
            **(execution.execution_metadata or {}),
            _METADATA_KEY: {
                **(execution.execution_metadata or {}).get(_METADATA_KEY, {}),
                "scheduling_state": "confirmed",
                "temporal_run_id": acceptance.temporal_run_id,
                "confirmed_at": changed.execution_confirmed_at.isoformat() if changed.execution_confirmed_at else None,
            },
        }
        await self.session.flush()
        return self._terminal(changed)

    async def finalize_without_execution(
        self, claim: DeliveryClaim, state: DeliveryState
    ) -> TerminalDelivery | ClaimLost:
        """Persist a no-trigger decision; it cannot overwrite prepared/accepted work."""
        if state not in {DeliveryState.FILTERED, DeliveryState.REJECTED, DeliveryState.CANCELLED}:
            msg = "A terminal no-trigger state is required"
            raise ValueError(msg)
        row = await self._current(claim)
        if row is None:
            return ClaimLost()
        if row.frozen_binding is not None or row.attempt_count or row.temporal_run_id is not None:
            msg = "Prepared or ambiguous work cannot be resolved without its Execution"
            raise ValueError(msg)
        changed = await self._change(claim, state=state.value, resolved_at=func.clock_timestamp())
        return ClaimLost() if changed is None else self._terminal(changed)

    async def defer(self, claim: DeliveryClaim, *, next_attempt_at: datetime, error_code: str) -> ClaimLost | None:
        """Release current ownership for retry without removing frozen or ambiguous evidence."""
        if re.fullmatch(r"[a-z][a-z0-9_]{0,99}", error_code) is None:
            msg = "A bounded sanitized error code is required"
            raise ValueError(msg)
        if next_attempt_at.tzinfo is None:
            msg = "Retry time must be timezone-aware"
            raise ValueError(msg)
        if await self._current(claim) is None:
            return ClaimLost()
        changed = await self._change(
            claim,
            next_attempt_at=next_attempt_at,
            last_error_code=error_code,
            claim_token=None,
            owner_worker_id=None,
            lease_until=None,
        )
        return ClaimLost() if changed is None else None

    async def lookup_terminal(self, identity: DeliveryIdentity) -> TerminalDelivery | None:
        """Verify canonical terminal evidence directly in PostgreSQL, even on a cache hit."""
        row = await self.session.get(EventDelivery, identity.digest, populate_existing=True)
        if row is None or row.state == DeliveryState.IN_PROGRESS:
            return None
        if row.delivery_identity() != identity:
            msg = "Retained terminal identity does not match the requested record"
            raise ValueError(msg)
        return self._terminal(row)

    async def claim_due(self, owner_worker_id: str, *, limit: int) -> list[DeliveryClaim]:
        """Claim a bounded due batch using lifecycle-before-delivery lock ordering."""
        self._validate_worker(owner_worker_id)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= FieldLimits.MAX_ITEMS_PER_PAGE:
            msg = "Recovery batch size must be between 1 and 100"
            raise ValueError(msg)
        candidates = (
            await self.session.exec(
                select(EventDelivery)
                .where(
                    col(EventDelivery.state) == DeliveryState.IN_PROGRESS.value,
                    col(EventDelivery.next_attempt_at) <= func.clock_timestamp(),
                    or_(
                        col(EventDelivery.lease_until).is_(None),
                        col(EventDelivery.lease_until) <= func.clock_timestamp(),
                    ),
                )
                .order_by(col(EventDelivery.next_attempt_at), col(EventDelivery.identity_digest))
                .limit(limit)
            )
        ).all()
        identities = [row.delivery_identity() for row in candidates]
        claims: list[DeliveryClaim] = []
        for identity in sorted(
            identities, key=lambda item: (item.workflow_id, item.subscription_id, item.source_id, item.digest)
        ):
            lifecycle = await lock_source_lifecycle(self.session, identity.source_id)
            if lifecycle is None or not self._matches_scope(identity, *lifecycle):
                continue
            row = await self._delivery(identity, skip_locked=True)
            if row is None or row.state != DeliveryState.IN_PROGRESS:
                continue
            result = await self._takeover(row, owner_worker_id)
            if isinstance(result, DeliveryClaim):
                claims.append(result)
        return claims
