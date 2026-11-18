"""Project typed source configuration from validated Subscribe parameters.

All transport-specific projection — the Kafka consumer-group identifier format
and the topic-to-configuration mapping — lives here in the adapters layer. The
neutral subscription service dispatches through these functions and never names a
transport directly.
"""

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from syntara.core.exceptions import SafeValueError
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.adapters.source_configuration import SourceConfigurationTypes
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

    Omitted groups are generated per source generation. Verified broker metadata
    is populated later by the worker, never accepted from Subscribe parameters.
    """
    if isinstance(parameters, KafkaSubscribeParameters):
        group_id = parameters.group_id or f"{_GROUP_ID_PREFIX}.{deployment_id}.{subscription_id}.{generation}"
        return KafkaSourceConfiguration(topic=parameters.topic, group_id=group_id, start=parameters.start)

    msg = "Unsupported Event Subscribe transport for source projection"
    raise ValueError(msg)


def update_source_configuration(
    configuration: EventSourceConfiguration, parameters: EventSubscribeParameters
) -> SourceConfigurationTypes:
    """Update reading policies while preserving a published source's fixed group and history."""
    if isinstance(configuration, KafkaSourceConfiguration) and isinstance(parameters, KafkaSubscribeParameters):
        if parameters.group_id is not None and parameters.group_id != configuration.group_id:
            msg = "Event Subscribe group_id is fixed after the first successful publication"
            raise SafeValueError(msg)
        return configuration.model_copy(update={"start": parameters.start})

    msg = "Unsupported Event Subscribe transport for source projection"
    raise ValueError(msg)


def source_configuration_error(error: IntegrityError) -> SafeValueError | None:
    """Map adapter-specific database constraints without exposing database details."""
    if "ix_event_subscription_sources_kafka_group_id" in str(error.orig):
        msg = "Event Subscribe group_id is already assigned to another source"
        return SafeValueError(msg)
    return None


def source_address_identity(configuration: EventSourceConfiguration) -> tuple[str, ...]:
    """Return the transport-address identity used to detect source replacement.

    Two configurations with the same integration but a different address (for
    Kafka, a different topic) are different source generations.
    """
    if isinstance(configuration, KafkaSourceConfiguration):
        return (configuration.transport, configuration.topic)

    msg = "Unsupported source configuration for identity comparison"
    raise ValueError(msg)
