"""Bounded runtime-credential checks using only non-creating Kafka metadata.

No consumer or group coordinator is constructed. A direct connection avoids the
client's implicit bootstrap/background metadata requests. Only Metadata v4/v5
can be negotiated, so older brokers cannot silently drop the creation flag.
"""

import asyncio
import ssl
from datetime import UTC, datetime
from typing import Any

from aiokafka.conn import AIOKafkaConnection, collect_hosts, create_conn
from aiokafka.errors import IncompatibleBrokerVersion, KafkaError
from aiokafka.protocol.api import Request
from aiokafka.protocol.metadata import MetadataRequest_v4, MetadataRequest_v5

from syntara.eventstreams.models.responses import EventSubscriptionTestResponse
from syntara.integrations.adapters.kafka import KafkaAdapter
from syntara.integrations.models.integration_configuration import KafkaConfiguration

_PREFLIGHT_TIMEOUT_SECONDS = 10
_CLOSE_TIMEOUT_SECONDS = 1


class NonCreatingMetadataRequest(Request[MetadataRequest_v4 | MetadataRequest_v5]):  # type: ignore[misc]  # aiokafka has no typing marker
    """Refuse protocol versions without explicit auto-creation control."""

    API_KEY = 3

    def __init__(self, topic: str) -> None:
        """Request exactly the unsaved topic, without group membership."""
        self.topic = topic

    def build(
        self, request_struct_class: type[MetadataRequest_v4 | MetadataRequest_v5]
    ) -> MetadataRequest_v4 | MetadataRequest_v5:
        """Encode the required non-creating metadata option."""
        return request_struct_class(topics=[self.topic], allow_auto_topic_creation=False)


async def _connect(config: KafkaConfiguration, options: dict[str, Any]) -> AIOKafkaConnection | None:
    for host, port, _ in collect_hosts(list(config.bootstrap_servers), randomize=False):
        try:
            return await create_conn(host, port, **options)
        except (OSError, KafkaError):
            continue
    return None


async def _close(connection: AIOKafkaConnection) -> None:
    try:
        async with asyncio.timeout(_CLOSE_TIMEOUT_SECONDS):
            closed = connection.close()
            if closed is not None:
                await closed
    except (TimeoutError, OSError, KafkaError):
        pass


async def test_kafka_connection(
    config: KafkaConfiguration, credential: dict[str, Any], topic: str
) -> EventSubscriptionTestResponse:
    """Authenticate and inspect metadata within one total network deadline."""
    result = EventSubscriptionTestResponse(success=False, checked_at=datetime.now(UTC))
    if not credential.get("kafka_username") or not credential.get("kafka_password"):
        result.error_code = "authentication_configuration"
        return result
    connection = None
    try:
        options = KafkaAdapter(config).connection_options(credential, _PREFLIGHT_TIMEOUT_SECONDS)
        async with asyncio.timeout(_PREFLIGHT_TIMEOUT_SECONDS):
            connection = await _connect(config, options)
            if connection is None:
                result.connection = "failed"
                result.error_code = "connection_failed"
                return result
            result.connection = "verified"
            response = await connection.send(NonCreatingMetadataRequest(topic))
            topics = [entry for entry in response.topics if entry[1] == topic]
            if not topics or topics[0][0] != 0 or not topics[0][3] or any(p[0] != 0 for p in topics[0][3]):
                result.topic_metadata = "failed"
                result.error_code = "topic_metadata_unavailable"
            else:
                result.topic_metadata = "verified"
                result.success = True
    except TimeoutError:
        result.error_code = "timeout"
    except (IncompatibleBrokerVersion, NotImplementedError):
        result.error_code = "safe_metadata_unsupported"
    except ssl.SSLError:
        result.error_code = "tls_failed"
    except (OSError, KafkaError):
        result.error_code = "connection_failed"
    finally:
        if connection is not None:
            await _close(connection)
    return result
