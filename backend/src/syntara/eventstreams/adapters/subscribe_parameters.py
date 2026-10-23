"""Select Subscribe definition schemas without importing broker clients."""

from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.core.subscribe_parameters import EventSubscribeParameters

# Keyed off the Integration type (resolved server-side), not a client-supplied
# field. Add a new transport by registering its Integration type and parameter
# subclass here — the published trigger contract does not change.
_PARAMETER_SCHEMAS: dict[str, type[EventSubscribeParameters]] = {
    "kafka": KafkaSubscribeParameters,
}


def validate_event_subscribe_parameters(
    parameters: object, *, integration_type: str | None = None
) -> EventSubscribeParameters:
    """Validate Subscribe parameters.

    Without ``integration_type`` (structural pass), validates the transport-neutral
    base contract. With ``integration_type`` (bind-time), selects the concrete
    transport schema for that Integration and enforces its transport-specific
    field rules — and rejects Integration types that cannot drive an event
    subscription.
    """
    if not isinstance(parameters, dict):
        msg = "Event Subscribe parameters must be an object"
        raise TypeError(msg)
    if integration_type is None:
        return EventSubscribeParameters.model_validate(parameters)
    schema = _PARAMETER_SCHEMAS.get(integration_type)
    if schema is None:
        msg = "Event Subscribe transport does not match the selected Integration type"
        raise ValueError(msg)
    return schema.model_validate(parameters)
