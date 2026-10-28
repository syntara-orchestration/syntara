"""Collect schema indexes for every supported transport; there is no default adapter."""

from sqlalchemy import Index

from syntara.eventstreams.adapters.kafka_delivery_indexes import kafka_delivery_indexes


def all_delivery_record_indexes() -> tuple[Index, ...]:
    """Register all adapter indexes; each index restricts rows by its transport."""
    return (*kafka_delivery_indexes(),)
