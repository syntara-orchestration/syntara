"""Project typed source configuration from validated Subscribe parameters.

All transport-specific projection — the Kafka consumer-group identifier format
and the topic-to-configuration mapping — lives here in the adapters layer. The
neutral subscription service dispatches through these functions and never names a
transport directly.
"""

from uuid import UUID

from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.source_configuration import EventSourceConfiguration
from syntara.eventstreams.core.subscribe_parameters import EventSubscribeParameters

# Stable, collision-resistant consumer-group prefix. Groups are keyed by
# deployment, subscription and source generation so a replaced source never
# reuses another stream's reading position.
_GROUP_ID_PREFIX = "syntara"


def project_source_configuration(
    parameters: EventSubscribeParameters,
    *,
    deployment_id: UUID,
    subscription_id: UUID,
    generation: int,
) -> EventSourceConfiguration:
    """Build the typed source configuration for one source generation.

    System-managed fields (the generated group ID) are added here; callers cannot
    supply them. An unsupported transport is rejected rather than silently
    projected.
    """
    if isinstance(parameters, KafkaSubscribeParameters):
        group_id = f"{_GROUP_ID_PREFIX}.{deployment_id}.{subscription_id}.{generation}"
        return KafkaSourceConfiguration(topic=parameters.topic, group_id=group_id)

    msg = "Unsupported Event Subscribe transport for source projection"
    raise ValueError(msg)


def source_address_identity(configuration: EventSourceConfiguration) -> tuple[str, ...]:
    """Return the transport-address identity used to detect source replacement.

    Two configurations with the same integration but a different address (for
    Kafka, a different topic) are different source generations.
    """
    if isinstance(configuration, KafkaSourceConfiguration):
        return (configuration.transport, configuration.topic)

    msg = "Unsupported source configuration for identity comparison"
    raise ValueError(msg)
