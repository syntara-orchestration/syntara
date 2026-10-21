"""Kafka metadata safety and independent protocol fixtures; no broker required."""

from uuid import UUID

import pytest
from aiokafka.protocol.metadata import MetadataResponse_v0, MetadataResponse_v5

from syntara.eventstreams.adapters.kafka_identity import (
    MetadataResponseV10,
    SourceMetadataRequest,
    decode_source_identity,
)
from syntara.eventstreams.core.consumer import IdentityStatus


@pytest.mark.parametrize(
    ("minimum", "maximum", "selected"), [(0, 0, 0), (0, 2, 2), (0, 4, 4), (0, 5, 5), (0, 9, 9), (9, 12, 10)]
)
def test_metadata_negotiation_cannot_create_topics(minimum: int, maximum: int, selected: int) -> None:
    request = SourceMetadataRequest("events.test").prepare({3: (minimum, maximum)})
    assert selected == request.API_VERSION
    fields = request.to_object()
    if selected < 4:
        assert fields["topics"] == ([] if selected == 0 else None)
    else:
        assert fields["allow_auto_topic_creation"] is False
        if selected < 9:
            assert fields["topics"] == ["events.test"]
        else:
            assert fields["topics"][0]["name"] == "events.test"
            assert fields["include_cluster_authorized_operations"] is False
            assert fields["include_topic_authorized_operations"] is False
            assert request.FLEXIBLE_VERSION
            if selected == 10:
                assert fields["topics"][0]["topic_id"] == UUID(int=0)


def test_metadata_v10_request_matches_kafka_wire_layout() -> None:
    request = SourceMetadataRequest("events.test").prepare({3: (9, 12)})
    # Compact array, nil UUID, compact exact name, topic tags, three false flags, root tags.
    expected = bytes.fromhex("02 00000000000000000000000000000000 0c 6576656e74732e74657374 00 00 00 00 00")
    assert request.encode() == expected


def test_metadata_v10_decodes_independent_wire_fixture() -> None:
    # Apache Kafka MetadataResponse v10 body, including a partition and an unknown root tag.
    # Kept independent of our Schema encoder so a wrong field order cannot round-trip unnoticed.
    body = bytes.fromhex(
        "00000000 02 00000001 07 62726f6b6572 00002384 00 00 "
        "0a 636c75737465722d41 00000001 02 0000 0c 6576656e74732e74657374 "
        "00112233445566778899aabbccddeeff 00 02 0000 00000000 00000001 00000007 "
        "02 00000001 02 00000001 01 00 80000000 00 80000000 01 02 01 7f"
    )
    response = MetadataResponseV10.decode(body)
    assert response.to_object()["tags"] == {2: b"\x7f"}
    assert response.to_object()["topics"][0]["partitions"][0]["leader_epoch"] == 7
    result = decode_source_identity(response, topic="events.test", epoch=42)
    assert result.assignment_epoch == 42
    assert result.cluster_id.status == IdentityStatus.VERIFIED
    assert result.cluster_id.value == "cluster-A"
    assert result.topic_id.status == IdentityStatus.VERIFIED
    assert result.topic_id.value == "ABEiM0RVZneImaq7zN3u_w"
    assert "broker" not in result.model_dump_json()


@pytest.mark.parametrize(
    ("name", "error", "identifier", "status"),
    [
        ("events.test", 0, UUID(int=1), IdentityStatus.VERIFIED),
        ("events.test", 0, UUID(int=0), IdentityStatus.UNCERTAIN),
        ("other-topic", 0, UUID(int=1), IdentityStatus.UNCERTAIN),
        ("events.test", 3, UUID(int=1), IdentityStatus.UNKNOWN_TOPIC),
        ("events.test", 29, UUID(int=1), IdentityStatus.UNAVAILABLE),
    ],
)
def test_exact_topic_evidence_is_independent_of_missing_cluster(
    name: str, error: int, identifier: UUID, status: IdentityStatus
) -> None:
    response = MetadataResponseV10(
        throttle_time_ms=0,
        brokers=[],
        cluster_id=None,
        controller_id=1,
        topics=[(error, name, identifier, False, [], 0, {})],
        cluster_authorized_operations=0,
        tags={},
    )
    result = decode_source_identity(response, topic="events.test", epoch=1)
    assert result.cluster_id.status == IdentityStatus.UNCERTAIN
    assert result.cluster_id.value is None
    assert result.topic_id.status == status
    assert (result.topic_id.value is not None) == (status == IdentityStatus.VERIFIED)


def test_legacy_protocols_report_unsupported_identity_explicitly() -> None:
    response = MetadataResponse_v5(
        throttle_time_ms=0,
        brokers=[],
        cluster_id="cluster-A",
        controller_id=1,
        topics=[(0, "events.test", False, [])],
    )
    result = decode_source_identity(response, topic="events.test", epoch=1)
    assert result.cluster_id.value == "cluster-A"
    assert result.topic_id.status == IdentityStatus.UNSUPPORTED
    oldest = MetadataResponse_v0(brokers=[], topics=[(0, "events.test", [])])
    result = decode_source_identity(oldest, topic="events.test", epoch=1)
    assert result.cluster_id.status == IdentityStatus.UNSUPPORTED
    assert result.topic_id.status == IdentityStatus.UNSUPPORTED
    absent = decode_source_identity(oldest, topic="not-visible", epoch=1)
    assert absent.topic_id.status == IdentityStatus.UNCERTAIN
