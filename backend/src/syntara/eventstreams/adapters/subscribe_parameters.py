"""Select Subscribe definition schemas without importing broker clients."""

from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeDraftParameters, KafkaSubscribeParameters
from syntara.eventstreams.core.draft_parameters import EventSubscribeDraftParameters
from syntara.eventstreams.core.subscribe_parameters import EventSubscribeParameters

# Keyed off the Integration type (resolved server-side), not a client-supplied
# field. Add a new transport by registering its Integration type and parameter
# subclass here — the published trigger contract does not change.
_PARAMETER_SCHEMAS: dict[str, type[EventSubscribeParameters]] = {
    "kafka": KafkaSubscribeParameters,
}


_DRAFT_PARAMETER_SCHEMAS: dict[str, type[EventSubscribeDraftParameters]] = {
    "kafka": KafkaSubscribeDraftParameters,
}

_KAFKA_PARAMETER_FIELDS = frozenset({"start", "group_id"})


def validate_event_subscribe_draft_parameters(
    parameters: object, *, integration_type: str | None = None
) -> EventSubscribeDraftParameters:
    """Validate supplied draft fields without making the draft executable."""
    if not isinstance(parameters, dict):
        msg = "Event Subscribe parameters must be an object"
        raise TypeError(msg)
    if integration_type is None:
        if not _KAFKA_PARAMETER_FIELDS.isdisjoint(parameters):
            return KafkaSubscribeDraftParameters.model_validate(parameters)
        return EventSubscribeDraftParameters.model_validate(parameters)
    schema = _DRAFT_PARAMETER_SCHEMAS.get(integration_type)
    if schema is None:
        msg = "Event Subscribe transport does not match the selected Integration type"
        raise ValueError(msg)
    return schema.model_validate(parameters)


def validate_event_subscribe_parameters(
    parameters: object, *, integration_type: str | None = None
) -> EventSubscribeParameters:
    """Validate Subscribe parameters.

    Without ``integration_type`` (structural pass), validates the common contract
    or the Kafka contract when Kafka-only controls are supplied. This preserves
    those controls for later binding validation without adding them to the neutral
    models. With ``integration_type`` (bind-time), selects the concrete schema
    for that Integration and rejects unsupported Integration types.
    """
    if not isinstance(parameters, dict):
        msg = "Event Subscribe parameters must be an object"
        raise TypeError(msg)
    if integration_type is None:
        if not _KAFKA_PARAMETER_FIELDS.isdisjoint(parameters):
            return KafkaSubscribeParameters.model_validate(parameters)
        return EventSubscribeParameters.model_validate(parameters)
    schema = _PARAMETER_SCHEMAS.get(integration_type)
    if schema is None:
        msg = "Event Subscribe transport does not match the selected Integration type"
        raise ValueError(msg)
    return schema.model_validate(parameters)
