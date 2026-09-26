"""WorkStore — the only path for mutating WorkItem state.

Nothing outside this module should construct, modify, or commit WorkItem
objects. The public methods express the intended lifecycle transitions;
any state not reachable through them is not a valid transition.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlmodel import col

from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import ExecutionTarget, TargetStatus
from execution_plane.models.work_item import WorkItem, WorkItemStatus
from execution_plane.store_base import StoreBase

_NOTIFY_CHANNEL = "execution_plane_work_items"


class WorkItemNotFoundError(LookupError):
    """Raised when a lifecycle transition targets an unknown work item."""

    def __init__(self, item_id: uuid.UUID) -> None:
        """Identify the missing work item."""
        super().__init__(f"Work item {item_id} does not exist")


class WorkStore(StoreBase):
    """Persist work item lifecycle transitions and own database resources."""

    async def dispatch(
        self,
        activity_handle: str,
        work_correlation_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> WorkItem:
        """Insert a new PENDING WorkItem and wake the EP worker via pg_notify."""
        item = WorkItem(
            id=uuid.uuid4(),
            work_correlation_id=work_correlation_id,
            activity_handle=activity_handle,
            status=WorkItemStatus.PENDING,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        async with self._session_context() as session:
            try:
                session.add(item)
                # pg_notify is transactional — delivered only after this commit.
                await session.execute(text(f"SELECT pg_notify('{_NOTIFY_CHANNEL}', '')"))
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return item

    async def claim_one(self) -> WorkItem | None:
        """Claim the oldest PENDING item for this worker, or return None."""
        async with self._session_context() as session:
            try:
                result = await session.execute(
                    select(WorkItem)
                    .where(col(WorkItem.status) == WorkItemStatus.PENDING)
                    .order_by(col(WorkItem.created_at))
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                item = result.scalars().first()
                if item is None:
                    return None
                # ============================================================
                # This places all WorkItems in the first default ExecutionTarget.
                # It will be updated to use the id for the ExecutionTarget identified
                # by the ExecutionTargetReconciler when implemented.
                # ------------------------------------------------------------
                target_result = await session.execute(
                    select(col(ExecutionTarget.id))
                    .join(Cluster, col(Cluster.id) == col(ExecutionTarget.cluster_id))
                    .where(col(ExecutionTarget.enabled).is_(True))
                    .where(col(ExecutionTarget.status) == TargetStatus.ACTIVE)
                    .where(col(Cluster.enabled).is_(True))
                    .where(col(Cluster.status) == ClusterStatus.ACTIVE)
                    .order_by(col(ExecutionTarget.is_default).desc(), col(ExecutionTarget.id))
                    .limit(1)
                    .with_for_update(skip_locked=True, of=ExecutionTarget)
                )
                target_id = target_result.scalar_one_or_none()
                if target_id is None:
                    return None
                item.execution_target_id = target_id
                # ============================================================
                item.status = WorkItemStatus.CLAIMED
                item.claimed_at = datetime.now(UTC)
                await session.commit()
                return item
            except Exception:
                await session.rollback()
                raise

    async def set_result(
        self,
        item_id: uuid.UUID,
        result: dict[str, Any],
        status: WorkItemStatus,
    ) -> WorkItem:
        """Persist the terminal result before signalling Temporal.

        Committing here means the startup recovery pass can retry the signal
        if the process crashes between this commit and mark_signal_delivered.
        """
        async with self._session_context() as session:
            try:
                item = await session.get(WorkItem, item_id)
                if item is None:
                    raise WorkItemNotFoundError(item_id)  # noqa: TRY301
                item.result = result
                item.status = status
                item.completed_at = datetime.now(UTC)
                await session.commit()
                return item
            except Exception:
                await session.rollback()
                raise

    async def mark_signal_delivered(self, item_id: uuid.UUID) -> None:
        """Record that the Temporal async-completion callback was confirmed sent."""
        async with self._session_context() as session:
            try:
                item = await session.get(WorkItem, item_id)
                if item is None:
                    raise WorkItemNotFoundError(item_id)  # noqa: TRY301
                item.signaled_at = datetime.now(UTC)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def find_undelivered(self) -> list[WorkItem]:
        """Return terminal items whose Temporal signal was never confirmed."""
        async with self._session_context() as session:
            result = await session.execute(
                select(WorkItem)
                .where(col(WorkItem.status).in_([WorkItemStatus.COMPLETED, WorkItemStatus.FAILED]))
                .where(col(WorkItem.signaled_at).is_(None))
            )
            return list(result.scalars().all())

    async def is_target_drained(self, target_id: uuid.UUID) -> bool:
        """Return whether no claimed or dispatched work remains on a target."""
        async with self._session_context() as session:
            result = await session.execute(
                select(col(WorkItem.id))
                .where(col(WorkItem.execution_target_id) == target_id)
                .where(col(WorkItem.status).in_([WorkItemStatus.CLAIMED, WorkItemStatus.DISPATCHED]))
                .limit(1)
            )
            return result.scalar_one_or_none() is None
