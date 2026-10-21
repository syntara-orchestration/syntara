"""Bounded Kafka partition evidence reads; no claims or acknowledgements."""

from collections.abc import Callable

from sqlalchemy import BigInteger, or_
from sqlalchemy import cast as sql_cast
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.deduplication import DeliveryIdentity, DeliveryState
from syntara.eventstreams.core.processing import CONTENT_INSPECTION_PENDING
from syntara.eventstreams.core.results import EventFailureCode
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot


class KafkaDeliveryReader:
    """Read one partition's recovery dependencies in numeric offset order."""

    def __init__(self, session_factory: Callable[..., AsyncSession]) -> None:
        """Inject a fresh session factory, shared with completed durable services."""
        self._session_factory = session_factory

    async def first_pending(self, snapshot: SubscriptionSnapshot, partition: int) -> DeliveryIdentity | None:
        """Find prepared or gated work that must precede later partition admissions."""
        async with self._session_factory() as session, session.begin():
            row = (
                await session.exec(
                    select(EventDelivery)
                    .where(
                        col(EventDelivery.source_id) == snapshot.source_id,
                        col(EventDelivery.source_generation) == snapshot.source_generation,
                        col(EventDelivery.transport) == "kafka",
                        col(EventDelivery.record_identity)["partition"].as_integer() == partition,
                        or_(
                            (col(EventDelivery.state) == DeliveryState.IN_PROGRESS.value)
                            & col(EventDelivery.frozen_binding).is_not(None),
                            col(EventDelivery.state) == DeliveryState.REJECTED.value,
                            col(EventDelivery.last_error_code).in_(
                                [CONTENT_INSPECTION_PENDING, *(code.value for code in EventFailureCode)]
                            ),
                        ),
                    )
                    .order_by(sql_cast(col(EventDelivery.record_identity)["offset"].as_string(), BigInteger))
                    .limit(1)
                )
            ).one_or_none()
            return None if row is None else row.delivery_identity()

    async def has_content_gate(self, snapshot: SubscriptionSnapshot, partition: int) -> bool:
        """Check all retained errors, including those outside the currently fetched range."""
        async with self._session_factory() as session, session.begin():
            return (
                await session.exec(
                    select(EventDelivery.identity_digest)
                    .where(
                        col(EventDelivery.source_id) == snapshot.source_id,
                        col(EventDelivery.transport) == "kafka",
                        col(EventDelivery.record_identity)["partition"].as_integer() == partition,
                        or_(
                            col(EventDelivery.state) == DeliveryState.REJECTED.value,
                            col(EventDelivery.last_error_code).in_(
                                [CONTENT_INSPECTION_PENDING, *(code.value for code in EventFailureCode)]
                            ),
                        ),
                    )
                    .limit(1)
                )
            ).first() is not None
