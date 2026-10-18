"""Select Subscribe definition schemas without importing broker clients."""

from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.core.subscribe_parameters import EventSubscribeParameters

_PARAMETER_SCHEMAS: dict[str, type[EventSubscribeParameters]] = {
    "kafka": KafkaSubscribeParameters,
}


def validate_event_subscribe_parameters(
    parameters: object, *, integration_type: str | None = None
) -> EventSubscribeParameters:
    """Validate transport-specific fields and, when supplied, Integration compatibility."""
    if not isinstance(parameters, dict):
        msg = "Event Subscribe parameters must be an object"
        raise TypeError(msg)
    transport = parameters.get("transport")
    schema = _PARAMETER_SCHEMAS.get(transport) if isinstance(transport, str) else None
    if schema is None:
        msg = "Unsupported Event Subscribe transport"
        raise ValueError(msg)
    config = schema.model_validate(parameters)
    if integration_type is not None and config.transport != integration_type:
        msg = "Event Subscribe transport does not match the selected Integration type"
        raise ValueError(msg)
    return config
