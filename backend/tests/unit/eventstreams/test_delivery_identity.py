"""Fixed consumer vectors and transport-scoped deterministic delivery identities."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.core.deduplication import DeliveryIdentity, input_fingerprint

# Generated independently with Node crypto (SHA-256 and RFC 4122 UUIDv5).
IDENTITY_TEST_VECTORS = (
    (0, "a68de4b752bc3e069611db98da61d83ee031a7758e5d1657c24db41e53b20232", "00aeddbb-7e21-5634-bd73-8d4a729efdda"),
    (
        9223372036854775807,
        "ae7d88154b5fdedac12bdf0f5d31b2a7d424d6999e9184d91aecb56e336bf3d6",
        "bca9151d-5211-5820-a084-84dfd1c824d1",
    ),
)


def identity(*, offset: int = 0) -> DeliveryIdentity:
    """Construct the fixed, publicly reproducible vector scope."""
    return DeliveryIdentity(
        deployment_id=UUID(int=1),
        integration_identity=UUID(int=2),
        source_id=UUID(int=3),
        workflow_id=UUID(int=4),
        subscription_id=UUID(int=5),
        source_generation=1,
        record=KafkaRecordIdentity(topic="orders", partition=2, offset=offset),
    )


@pytest.mark.parametrize(("offset", "digest", "execution_id"), IDENTITY_TEST_VECTORS)
def test_fixed_vectors(offset: int, digest: str, execution_id: str) -> None:
    """All derived identities agree with independent fixed vectors."""
    value = identity(offset=offset)
    assert value.digest == digest
    assert str(value.execution_id) == execution_id
    assert value.temporal_workflow_id == f"event-v1-{digest}"
    assert value.cache_key == f"syntara:eventstreams:dedup:v1:{digest}"
    assert DeliveryIdentity.model_validate_json(value.model_dump_json()) == value
    assert f'"offset":"{offset}"'.encode() in value.canonical_bytes()


def test_canonical_encoding_is_fixed() -> None:
    """Field ordering, version, UTF-8/ASCII encoding and whitespace are fixed."""
    assert identity().canonical_bytes() == (
        b'{"deployment_id":"00000000-0000-0000-0000-000000000001","identity_version":1,'
        b'"integration_identity":"00000000-0000-0000-0000-000000000002",'
        b'"record":{"offset":"0","partition":2,"topic":"orders","transport":"kafka"},'
        b'"source_generation":1,"source_id":"00000000-0000-0000-0000-000000000003",'
        b'"subscription_id":"00000000-0000-0000-0000-000000000005",'
        b'"workflow_id":"00000000-0000-0000-0000-000000000004"}'
    )


@pytest.mark.parametrize(
    "field",
    ["deployment_id", "integration_identity", "source_id", "workflow_id", "subscription_id", "source_generation"],
)
def test_every_scope_component_distinguishes_identity(field: str) -> None:
    """Independent subscriptions/deployments/source generations cannot share identity."""
    original = identity()
    values = original.model_dump()
    values[field] = 2 if field == "source_generation" else UUID(int=99)
    changed = DeliveryIdentity.model_validate(values)
    assert changed.digest != original.digest
    assert changed.execution_id != original.execution_id
    assert changed.temporal_workflow_id != original.temporal_workflow_id


@pytest.mark.parametrize("field", ["workflow_name", "workflow_version_id", "worker_id", "payload", "secret"])
def test_mutable_or_sensitive_fields_are_not_identity_inputs(field: str) -> None:
    """Renames and retries have no representation in canonical identity."""
    values = identity().model_dump()
    values[field] = "ignored"
    with pytest.raises(ValidationError):
        DeliveryIdentity.model_validate(values)


@pytest.mark.parametrize("updates", [{"topic": "other"}, {"partition": 3}, {"offset": 1}])
def test_each_record_coordinate_distinguishes_identity(updates: dict[str, object]) -> None:
    """Different source records remain distinct, even with identical message bodies."""
    original = identity()
    values = original.model_dump()
    values["record"] = original.record.model_dump() | updates
    assert DeliveryIdentity.model_validate(values).digest != original.digest


@pytest.mark.parametrize("offset", [-1, 2**63, True, "01", "-1", "1.0", "\u0661", ""])
def test_offset_bounds_and_lossless_encoding(offset: object) -> None:
    """Offsets reject overflow, booleans and noncanonical decimal strings."""
    with pytest.raises(ValidationError):
        KafkaRecordIdentity(topic="orders", partition=0, offset=offset)


def test_identity_and_record_are_immutable() -> None:
    """Nested coordinates cannot change the digest after claim creation."""
    value = identity()
    with pytest.raises(ValidationError):
        value.source_generation = 2
    with pytest.raises(ValidationError):
        value.record.offset = 1


def test_fingerprint_is_stable_and_context_sensitive() -> None:
    """Fingerprints bind frozen input and context without storing their contents."""
    assert input_fingerprint({"b": 2, "a": 1}, {"x": 3}) == input_fingerprint({"a": 1, "b": 2}, {"x": 3})
    assert input_fingerprint({"a": 1}, {}) != input_fingerprint({"a": 1}, {"version": 2})
