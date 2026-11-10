"""Pin producer sockets without modifying aiokafka's module globals or lifecycle.

aiokafka 0.14 has no connection-factory hook. Its bootstrap and broker-connection
methods use a module-level create_conn. Bind copies of those upstream methods
with a private globals dictionary to this producer's existing client. All other
client, sender, accumulator and producer behavior remains upstream-owned.
"""

from functools import update_wrapper
from types import FunctionType, MethodType

from aiokafka import AIOKafkaProducer
from aiokafka.client import AIOKafkaClient

from syntara.integrations.lib.kafka_connection import create_pinned_connection


def _pinned_method(method: FunctionType) -> FunctionType:
    if "create_conn" not in method.__code__.co_names:
        msg = "Unsupported aiokafka connection-factory layout"
        raise RuntimeError(msg)
    pinned = FunctionType(
        method.__code__,
        {**method.__globals__, "create_conn": create_pinned_connection},
        method.__name__,
        method.__defaults__,
        method.__closure__,
    )
    pinned.__kwdefaults__ = method.__kwdefaults__
    update_wrapper(pinned, method)
    return pinned


def create_kafka_publish_producer(**options: object) -> AIOKafkaProducer:
    """Use the shared socket policy for bootstrap, metadata brokers and reconnects."""
    methods = {name: _pinned_method(getattr(AIOKafkaClient, name)) for name in ("bootstrap", "_get_conn")}
    producer = AIOKafkaProducer(**options)
    for name, method in methods.items():
        setattr(producer.client, name, MethodType(method, producer.client))
    return producer
