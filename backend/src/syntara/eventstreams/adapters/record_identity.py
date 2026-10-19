"""Supported record-coordinate variants; no broker clients are imported."""

from typing import Annotated

from pydantic import Field

from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.record_identity import EventRecordIdentity
from syntara.eventstreams.core.source_configuration import EventSourceConfiguration

RecordIdentityTypes = KafkaRecordIdentity
RecordIdentity = Annotated[RecordIdentityTypes, Field(discriminator="transport")]


def record_matches_source(record: EventRecordIdentity, configuration: EventSourceConfiguration) -> bool:
    """Dispatch supported adapter address checks; unsupported variants fail closed."""
    if isinstance(record, KafkaRecordIdentity) and isinstance(configuration, KafkaSourceConfiguration):
        return record.transport == configuration.transport and record.topic == configuration.topic
    return False
