"""Non-creating Kafka Metadata requests and identity evidence decoding.

aiokafka 0.14 ships Metadata schemas only through v5. This small extension adds
the v9/v10 schemas needed to negotiate with modern brokers and read topic IDs.
Wire layouts follow Apache Kafka's MetadataRequest/MetadataResponse definitions:
https://github.com/apache/kafka/tree/trunk/clients/src/main/resources/common/message
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from typing import TYPE_CHECKING
from uuid import UUID

from aiokafka.errors import UnknownTopicOrPartitionError
from aiokafka.protocol.abstract import AbstractType
from aiokafka.protocol.api import Request, RequestStruct, Response
from aiokafka.protocol.metadata import MetadataRequest_v2, MetadataRequest_v4, MetadataRequestStruct
from aiokafka.protocol.types import Boolean, CompactArray, CompactString, Int16, Int32, Schema, TaggedFields

from syntara.eventstreams.core.consumer import (
    IdentityObservation,
    IdentityStatus,
    PartitionSetObservation,
    PartitionSetStatus,
    SourceIdentityObservation,
)

if TYPE_CHECKING:
    from io import BytesIO

    from aiokafka.protocol.types import ValueT


class _KafkaUuid(AbstractType[UUID]):
    @classmethod
    def encode(cls, value: UUID) -> bytes:
        return value.bytes

    @classmethod
    def decode(cls, data: BytesIO) -> UUID:
        return UUID(bytes=data.read(16))


def _response_schema(*, with_topic_id: bool) -> Schema:
    topic_fields: list[tuple[str, ValueT]] = [("error_code", Int16), ("name", CompactString("utf-8"))]
    if with_topic_id:
        topic_fields.append(("topic_id", _KafkaUuid))
    return Schema(
        ("throttle_time_ms", Int32),
        (
            "brokers",
            CompactArray(
                ("node_id", Int32),
                ("host", CompactString("utf-8")),
                ("port", Int32),
                ("rack", CompactString("utf-8")),
                ("tags", TaggedFields),
            ),
        ),
        ("cluster_id", CompactString("utf-8")),
        ("controller_id", Int32),
        (
            "topics",
            CompactArray(
                *topic_fields,
                ("is_internal", Boolean),
                (
                    "partitions",
                    CompactArray(
                        ("error_code", Int16),
                        ("partition", Int32),
                        ("leader", Int32),
                        ("leader_epoch", Int32),
                        ("replicas", CompactArray(Int32)),
                        ("isr", CompactArray(Int32)),
                        ("offline_replicas", CompactArray(Int32)),
                        ("tags", TaggedFields),
                    ),
                ),
                ("topic_authorized_operations", Int32),
                ("tags", TaggedFields),
            ),
        ),
        ("cluster_authorized_operations", Int32),
        ("tags", TaggedFields),
    )


class MetadataResponseV9(Response):
    """Flexible Metadata response without topic identifiers."""

    API_KEY = 3
    API_VERSION = 9
    SCHEMA = _response_schema(with_topic_id=False)


class MetadataResponseV10(Response):
    """Flexible Metadata response including topic UUIDs."""

    API_KEY = 3
    API_VERSION = 10
    SCHEMA = _response_schema(with_topic_id=True)


class MetadataRequestV9(RequestStruct):
    """Exact-name metadata lookup with auto-creation explicitly disabled."""

    API_KEY = 3
    API_VERSION = 9
    FLEXIBLE_VERSION = True
    RESPONSE_TYPE = MetadataResponseV9
    SCHEMA = Schema(
        ("topics", CompactArray(("name", CompactString("utf-8")), ("tags", TaggedFields))),
        ("allow_auto_topic_creation", Boolean),
        ("include_cluster_authorized_operations", Boolean),
        ("include_topic_authorized_operations", Boolean),
        ("tags", TaggedFields),
    )


class MetadataRequestV10(RequestStruct):
    """Topic-ID capable lookup by exact name, with the request UUID unset."""

    API_KEY = 3
    API_VERSION = 10
    FLEXIBLE_VERSION = True
    RESPONSE_TYPE = MetadataResponseV10
    SCHEMA = Schema(
        ("topics", CompactArray(("topic_id", _KafkaUuid), ("name", CompactString("utf-8")), ("tags", TaggedFields))),
        ("allow_auto_topic_creation", Boolean),
        ("include_cluster_authorized_operations", Boolean),
        ("include_topic_authorized_operations", Boolean),
        ("tags", TaggedFields),
    )


IdentityRequestStruct = MetadataRequestStruct | MetadataRequestV9 | MetadataRequestV10


class SourceMetadataRequest(Request[IdentityRequestStruct]):
    """Negotiate metadata without permitting customer-topic creation.

    Versions below v4 cannot disable creation for a named topic, so those
    versions request all visible topics instead. A missing topic in that
    response is uncertain evidence, not proof that the topic does not exist.
    """

    API_KEY = 3

    def __init__(self, topic: str) -> None:
        """Fix the exact source topic for this request."""
        self.topic = topic

    def build(self, request_struct_class: type[IdentityRequestStruct]) -> IdentityRequestStruct:
        """Build the negotiated wire version without topic-creation side effects."""
        version = request_struct_class.API_VERSION
        if version >= MetadataRequestV9.API_VERSION:
            topics: list[tuple[object, ...]] = (
                [(UUID(int=0), self.topic, dict[int, bytes]())]
                if version >= MetadataRequestV10.API_VERSION
                else [(self.topic, dict[int, bytes]())]
            )
            return request_struct_class(
                topics=topics,
                allow_auto_topic_creation=False,
                include_cluster_authorized_operations=False,
                include_topic_authorized_operations=False,
                tags={},
            )
        if version >= MetadataRequest_v4.API_VERSION:
            return request_struct_class(topics=[self.topic], allow_auto_topic_creation=False)
        return request_struct_class(topics=[] if version == 0 else None)


def _decode_partitions(topic_row: dict[str, object]) -> PartitionSetObservation:
    """Validate every partition in the broker's full-topic metadata snapshot."""
    error_code = topic_row.get("error_code")
    if type(error_code) is not int:
        return PartitionSetObservation(status=PartitionSetStatus.UNCERTAIN, error="topic error code missing or invalid")
    if error_code != 0:
        return PartitionSetObservation(status=PartitionSetStatus.UNAVAILABLE, error="topic metadata lookup failed")
    return _decode_partition_rows(topic_row.get("partitions"))


def _decode_partition_rows(rows: object) -> PartitionSetObservation:
    """Reject partial or malformed membership without filtering failed rows."""
    if not isinstance(rows, list) or not rows:
        return PartitionSetObservation(status=PartitionSetStatus.UNCERTAIN, error="partition metadata missing or empty")
    partition_ids: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            return PartitionSetObservation(status=PartitionSetStatus.UNCERTAIN, error="invalid partition metadata")
        partition = row.get("partition")
        error = row.get("error_code")
        if type(partition) is not int or not 0 <= partition <= (1 << 31) - 1 or type(error) is not int:
            return PartitionSetObservation(status=PartitionSetStatus.UNCERTAIN, error="invalid partition metadata")
        if error != 0:
            return PartitionSetObservation(
                status=PartitionSetStatus.UNAVAILABLE, error="partition metadata lookup failed"
            )
        partition_ids.append(partition)
    # Sorting also detects duplicates and gaps without silently deduplicating.
    ids = tuple(sorted(partition_ids))
    if any(partition != index for index, partition in enumerate(ids)):
        return PartitionSetObservation(
            status=PartitionSetStatus.UNCERTAIN, error="partition metadata duplicate or incomplete"
        )
    return PartitionSetObservation(status=PartitionSetStatus.VERIFIED, partition_ids=ids)


def decode_source_identity(response: Response, *, topic: str, epoch: int) -> SourceIdentityObservation:
    """Decode independent identity and full-topic partition evidence."""
    data = response.to_object()
    cluster_id = data.get("cluster_id")
    if response.API_VERSION < MetadataRequest_v2.API_VERSION:
        cluster = IdentityObservation(status=IdentityStatus.UNSUPPORTED, error="cluster identifier unsupported")
    elif isinstance(cluster_id, str) and cluster_id.strip():
        cluster = IdentityObservation(status=IdentityStatus.VERIFIED, value=cluster_id)
    else:
        cluster = IdentityObservation(status=IdentityStatus.UNCERTAIN, error="cluster identifier missing")

    rows = data.get("topics")
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("name", row.get("topic")), str) for row in rows
    ):
        rows = []
    topics = [row for row in rows if row.get("name", row.get("topic")) == topic]
    identity = IdentityObservation(
        status=IdentityStatus.UNCERTAIN, error="exact topic missing or ambiguous in metadata"
    )
    partitions = PartitionSetObservation(
        status=PartitionSetStatus.UNCERTAIN, error="exact topic missing or ambiguous in metadata"
    )
    if len(topics) == 1:
        row = topics[0]
        partitions = _decode_partitions(row)
        error_code = row.get("error_code")
        if type(error_code) is not int:
            identity = IdentityObservation(status=IdentityStatus.UNCERTAIN, error="topic error code missing or invalid")
        elif error_code == UnknownTopicOrPartitionError.errno:
            identity = IdentityObservation(status=IdentityStatus.UNKNOWN_TOPIC, error="topic is unknown to broker")
        elif error_code != 0:
            identity = IdentityObservation(status=IdentityStatus.UNAVAILABLE, error="topic metadata lookup failed")
        elif response.API_VERSION < MetadataRequestV10.API_VERSION:
            identity = IdentityObservation(status=IdentityStatus.UNSUPPORTED, error="topic identifier unsupported")
        else:
            topic_id = row.get("topic_id")
            if isinstance(topic_id, UUID) and topic_id.int != 0:
                identity = IdentityObservation(
                    status=IdentityStatus.VERIFIED,
                    value=urlsafe_b64encode(topic_id.bytes).decode("ascii").rstrip("="),
                )
            else:
                identity = IdentityObservation(status=IdentityStatus.UNCERTAIN, error="topic identifier missing")
    return SourceIdentityObservation(
        topic=topic, assignment_epoch=epoch, cluster_id=cluster, topic_id=identity, partitions=partitions
    )
