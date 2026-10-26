"""Kafka metadata safety and independent protocol fixtures; no broker required."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from aiokafka.protocol.metadata import MetadataResponse_v0, MetadataResponse_v5
from pydantic import ValidationError

from syntara.eventstreams.adapters.kafka_identity import (
    MetadataResponseV9,
    MetadataResponseV10,
    SourceMetadataRequest,
    decode_source_identity,
)
from syntara.eventstreams.core.consumer import IdentityStatus, PartitionSetObservation, PartitionSetStatus

if TYPE_CHECKING:
    from aiokafka.protocol.api import Response


@pytest.mark.parametrize(
    ("minimum", "maximum", "selected"),
    [(0, version, version) for version in (0, 1, 2, 3, 4, 5, 9, 10)]
    + [(0, version, 5) for version in (6, 7, 8)]
    + [(9, 12, 10)],
)
def test_metadata_negotiation_cannot_create_topics(minimum: int, maximum: int, selected: int) -> None:
    request = SourceMetadataRequest("events.test").prepare({3: (minimum, maximum)})
    assert selected == request.API_VERSION
    fields = request.to_object()
    assert type(request).decode(request.encode()).to_object() == fields
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
    assert result.partitions.status == PartitionSetStatus.VERIFIED
    assert result.partitions.partition_ids == (0,)
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


@pytest.mark.parametrize("version", [0, 5, 9, 10])
def test_partition_membership_is_independent_of_identifier_support(version: int) -> None:
    """Decode complete membership on legacy and flexible wire protocols."""
    partitions = [(0, partition, 1, [1], [1]) for partition in (2, 0, 1)]
    response: Response
    if version == 0:
        response = MetadataResponse_v0(brokers=[], topics=[(0, "events.test", partitions)])
    elif version == 5:
        response = MetadataResponse_v5(
            throttle_time_ms=0,
            brokers=[],
            cluster_id=None,
            controller_id=1,
            topics=[(0, "events.test", False, [(*row, []) for row in partitions])],
        )
    else:
        flexible_partitions: list[tuple[object, ...]] = [
            (0, partition, 1, 7, [1], [1], [], {}) for partition in (2, 0, 1)
        ]
        topic_fields: tuple[object, ...] = (0, "events.test")
        if version == 10:
            topic_fields += (UUID(int=0),)
        response_type = MetadataResponseV10 if version == 10 else MetadataResponseV9
        response = response_type(
            throttle_time_ms=0,
            brokers=[],
            cluster_id=None,
            controller_id=1,
            topics=[(*topic_fields, False, flexible_partitions, 0, {})],
            cluster_authorized_operations=0,
            tags={},
        )
    decoded = type(response).decode(response.encode())
    result = decode_source_identity(decoded, topic="events.test", epoch=1)
    assert result.partitions.status == PartitionSetStatus.VERIFIED
    assert result.partitions.partition_ids == (0, 1, 2)
    assert result.topic_id.status == (IdentityStatus.UNCERTAIN if version == 10 else IdentityStatus.UNSUPPORTED)
    assert result.cluster_id.status != IdentityStatus.VERIFIED


@pytest.mark.parametrize(
    ("partitions", "status"),
    [
        (None, PartitionSetStatus.UNCERTAIN),
        ([], PartitionSetStatus.UNCERTAIN),
        ({0: 0}, PartitionSetStatus.UNCERTAIN),
        ([None], PartitionSetStatus.UNCERTAIN),
        ([{}], PartitionSetStatus.UNCERTAIN),
        ([{"partition": 0}], PartitionSetStatus.UNCERTAIN),
        ([{"partition": 0, "error_code": False}], PartitionSetStatus.UNCERTAIN),
        ([{"partition": 0, "error_code": "0"}], PartitionSetStatus.UNCERTAIN),
        ([{"partition": 0, "error_code": 3}], PartitionSetStatus.UNAVAILABLE),
        ([{"partition": 0, "error_code": 29}], PartitionSetStatus.UNAVAILABLE),
        ([{"partition": 0, "error_code": 0}, {"partition": 1, "error_code": 5}], PartitionSetStatus.UNAVAILABLE),
        ([{"partition": 0, "error_code": 0}, {"partition": 2, "error_code": 0}], PartitionSetStatus.UNCERTAIN),
        ([{"partition": 1, "error_code": 0}], PartitionSetStatus.UNCERTAIN),
        ([{"partition": 0, "error_code": 0}] * 2, PartitionSetStatus.UNCERTAIN),
        *[
            ([{"partition": value, "error_code": 0}], PartitionSetStatus.UNCERTAIN)
            for value in (-1, True, "0", 0.0, None, 1 << 31)
        ],
    ],
)
def test_invalid_or_partial_partitions_never_verify_membership(partitions: object, status: PartitionSetStatus) -> None:
    response = MagicMock(API_VERSION=10)
    response.to_object.return_value = {
        "cluster_id": "cluster-A",
        "topics": [{"name": "events.test", "topic_id": UUID(int=1), "error_code": 0, "partitions": partitions}],
    }
    result = decode_source_identity(response, topic="events.test", epoch=1)
    assert result.partitions.status == status
    assert result.partitions.partition_ids is None
    assert result.topic_id.status == IdentityStatus.VERIFIED


@pytest.mark.parametrize(
    "topics",
    [
        None,
        [],
        [None],
        [{"name": "other-topic"}],
        [{"name": "events.test", "error_code": 0, "partitions": [{"partition": 0, "error_code": 0}]}, {}],
    ],
)
def test_missing_or_malformed_topics_cannot_verify_membership(topics: object) -> None:
    response = MagicMock(API_VERSION=10)
    response.to_object.return_value = {"topics": topics}
    result = decode_source_identity(response, topic="events.test", epoch=1)
    assert result.partitions.status == PartitionSetStatus.UNCERTAIN
    assert result.partitions.partition_ids is None


@pytest.mark.parametrize("error_code", [None, False, "0", 3, 29])
def test_topic_errors_cannot_verify_membership(error_code: object) -> None:
    response = MagicMock(API_VERSION=10)
    response.to_object.return_value = {
        "topics": [
            {"name": "events.test", "error_code": error_code, "partitions": [{"partition": 0, "error_code": 0}]}
        ],
    }
    result = decode_source_identity(response, topic="events.test", epoch=1)
    expected = PartitionSetStatus.UNAVAILABLE if type(error_code) is int else PartitionSetStatus.UNCERTAIN
    assert result.partitions.status == expected
    assert result.partitions.partition_ids is None


def test_duplicate_exact_topic_rows_cannot_verify_membership() -> None:
    response = MetadataResponse_v0(brokers=[], topics=[(0, "events.test", [(0, 0, 1, [1], [1])])] * 2)
    result = decode_source_identity(response, topic="events.test", epoch=1)
    assert result.partitions.status == PartitionSetStatus.UNCERTAIN
    assert result.partitions.partition_ids is None


@pytest.mark.parametrize("ids", [None, (), (0, 0), (0, 2), (1,), (-1,), (True,), ("0",), (0.0,), (1 << 31,)])
def test_verified_partition_contract_rejects_invalid_membership(ids: object) -> None:
    with pytest.raises(ValidationError):
        PartitionSetObservation.model_validate({"status": "verified", "partition_ids": ids})


@pytest.mark.parametrize("status", [PartitionSetStatus.UNAVAILABLE, PartitionSetStatus.UNCERTAIN])
def test_unverified_partition_contract_rejects_membership(status: PartitionSetStatus) -> None:
    with pytest.raises(ValidationError):
        PartitionSetObservation(status=status, partition_ids=(0,))


def test_partition_evidence_is_immutable() -> None:
    ids = [0, 1]
    result = PartitionSetObservation.model_validate({"status": "verified", "partition_ids": ids})
    ids.append(2)
    assert result.partition_ids == (0, 1)
    with pytest.raises(ValidationError):
        result.partition_ids = (0, 1, 2)
