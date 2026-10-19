"""Separate PostgreSQL retained-row-count check with shared hysteresis."""

from datetime import datetime, timedelta

import structlog
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.constants import EventDeliveryDefaults
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.delivery_capacity import EventDeliveryCapacity

logger = structlog.stdlib.get_logger(__name__)


def capacity_paused(*, retained_count: int, previously_paused: bool) -> bool:
    """Keep a paused deployment closed until count is strictly below the resume mark."""
    if retained_count < 0:
        msg = "Retained delivery count cannot be negative"
        raise ValueError(msg)
    if previously_paused:
        return retained_count >= EventDeliveryDefaults.CAPACITY_RESUME_ROWS
    return retained_count >= EventDeliveryDefaults.CAPACITY_PAUSE_ROWS


class PostgreSQLDeliveryCapacityCheck:
    """Session-bound soft admission gate; caller commits its shared snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        """Use the caller's short transaction, never a Redis capacity grant."""
        self.session = session

    @staticmethod
    def _fresh(row: EventDeliveryCapacity, now: datetime) -> bool:
        return row.checked_at is not None and timedelta(0) <= now - row.checked_at < timedelta(
            seconds=EventDeliveryDefaults.CAPACITY_CHECK_INTERVAL_SECONDS
        )

    async def permits_new_delivery(self) -> bool:
        """Fail closed when the separate count check or its stored state is unavailable."""
        try:
            # A failed optional measurement must not leave a healthy outer
            # transaction aborted. A database outage still prevents admission.
            async with self.session.begin_nested():
                now = (await self.session.exec(select(func.clock_timestamp()))).one()
                row = await self.session.get(EventDeliveryCapacity, 1, populate_existing=True)
                if row is not None and self._fresh(row, now):
                    return not row.paused
                await self.session.execute(
                    insert(EventDeliveryCapacity)
                    .values(id=1, paused=False, retained_count=0)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                row = (
                    await self.session.exec(
                        select(EventDeliveryCapacity)
                        .where(col(EventDeliveryCapacity.id) == 1)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).one()
                now = (await self.session.exec(select(func.clock_timestamp()))).one()
                if self._fresh(row, now):
                    return not row.paused
                count = (await self.session.exec(select(func.count()).select_from(EventDelivery))).one()
                row.paused = capacity_paused(retained_count=count, previously_paused=row.paused)
                row.retained_count = count
                row.checked_at = now
                await self.session.flush()
                return not row.paused
        except (SQLAlchemyError, OSError, TimeoutError):
            logger.warning("event_delivery_capacity_check_unavailable")
            return False
