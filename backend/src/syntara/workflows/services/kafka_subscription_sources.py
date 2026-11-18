"""Read workflow-authorized Kafka source metadata without scanning version history."""

from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters.source_projection import generated_kafka_group_id
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.workflows.models.workflow import KafkaSubscriptionSourceRead


async def read_kafka_subscription_sources(
    session: AsyncSession, workflow_id: UUID
) -> list[KafkaSubscriptionSourceRead]:
    """Return only the active generation of each retained subscription for this workflow."""
    rows = await session.exec(
        select(EventSubscription, EventSubscriptionSource)
        .join(
            EventSubscriptionSource,
            (col(EventSubscriptionSource.subscription_id) == col(EventSubscription.id))
            & (col(EventSubscriptionSource.generation) == col(EventSubscription.active_source_generation)),
        )
        .where(
            EventSubscription.workflow_id == workflow_id,
            col(EventSubscription.retired).is_(False),
            EventSubscriptionSource.transport == "kafka",
        )
        .order_by(EventSubscription.trigger_node_id)
    )
    sources = []
    for subscription, source in rows:
        configuration = source.configuration
        sources.append(
            KafkaSubscriptionSourceRead(
                trigger_node_id=subscription.trigger_node_id,
                source_id=source.id,
                generation=source.generation,
                configuration_revision=subscription.configuration_revision,
                integration_id=source.integration_identity,
                topic=configuration.topic,
                group_id=configuration.group_id,
                group_id_is_generated=configuration.group_id
                == generated_kafka_group_id(source.deployment_id, source.subscription_id, source.generation),
            )
        )
    return sources
