"""Kafka-specific BIGINT coordinate indexes for the common delivery ledger."""

from sqlalchemy import Index, text


def kafka_delivery_indexes() -> tuple[Index, ...]:
    """Keep Kafka partition/offset expressions outside the transport-neutral model."""
    return (
        Index(
            "ix_event_deliveries_kafka_position",
            "source_id",
            text("((record_identity->>'partition')::integer)"),
            text("((record_identity->>'offset')::bigint)"),
            postgresql_where=text("transport = 'kafka'"),
        ),
    )
