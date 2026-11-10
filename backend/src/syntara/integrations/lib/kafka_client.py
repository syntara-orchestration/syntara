"""Consumer client with the existing Integration policy on every Kafka socket.

aiokafka 0.14 has no connection-factory hook. These two connection-management
methods follow aiokafka.client.AIOKafkaClient (Apache-2.0), substituting only our
socket factory. Protocol, authentication, metadata refresh and group coordination
remain upstream. Keep the installed-library regression tests when upgrading it.
No process-wide aiokafka or event-loop state is patched.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from aiokafka.client import AIOKafkaClient, ConnectionGroup
from aiokafka.conn import AIOKafkaConnection, CloseReason
from aiokafka.errors import KafkaConnectionError, KafkaError, StaleMetadata
from aiokafka.protocol.metadata import MetadataRequest

from syntara.integrations.lib.kafka_connection import create_kafka_connection

if TYPE_CHECKING:
    from aiokafka.protocol.api import Request, Response


class KafkaPolicyClient(AIOKafkaClient):
    """Check and pin bootstrap, advertised broker and coordinator connections."""

    def __init__(self, **kwargs: object) -> None:
        """Keep the untyped upstream constructor at this library boundary."""
        super().__init__(**kwargs)  # type: ignore[no-untyped-call]

    def get_random_node(self) -> int | None:
        """Read a broker ID through the untyped upstream client."""
        return cast("int | None", super().get_random_node())  # type: ignore[no-untyped-call]

    async def send(
        self, node_id: int | str, request: Request[Any], *, group: ConnectionGroup = ConnectionGroup.DEFAULT
    ) -> Response | None:
        """Delegate protocol requests, including requests that require no response."""
        return cast("Response | None", await super().send(node_id, request, group=group))  # type: ignore[no-untyped-call]

    async def coordinator_lookup(self, coordinator_type: int, coordinator_key: str) -> int:
        """Resolve the coordinator through the untyped upstream client."""
        node = await super().coordinator_lookup(coordinator_type, coordinator_key)  # type: ignore[no-untyped-call]
        return cast("int", node)

    async def close(self) -> None:
        """Close owned sockets even if metadata shutdown fails or is cancelled."""
        try:
            await super().close()  # type: ignore[no-untyped-call]
        finally:
            # Upstream close awaits the metadata task before closing sockets.
            # A maintenance deadline or failed task must not leak those sockets.
            for connection in self._conns.values():
                connection.close(reason=CloseReason.SHUTDOWN)
            self._conns.clear()
            if self._sync_task is not None and self._sync_task.done():
                self._sync_task = None

    async def _connect(self, host: str, port: int) -> AIOKafkaConnection:
        return await create_kafka_connection(
            host,
            port,
            client_id=self._client_id,
            request_timeout_ms=self._request_timeout_ms,
            ssl_context=self._ssl_context,
            security_protocol=self._security_protocol,
            max_idle_ms=self._connections_max_idle_ms,
            on_close=self._on_connection_closed,
            sasl_mechanism=self._sasl_mechanism,
            sasl_plain_username=self._sasl_plain_username,
            sasl_plain_password=self._sasl_plain_password,
            sasl_kerberos_service_name=self._sasl_kerberos_service_name,
            sasl_kerberos_domain_name=self._sasl_kerberos_domain_name,
            sasl_oauth_token_provider=self._sasl_oauth_token_provider,
        )

    async def bootstrap(self) -> None:
        """Bootstrap using protected sockets, retaining upstream metadata behavior."""
        if self._loop is not asyncio.get_running_loop():
            msg = "Kafka client must start on its creating event loop"
            raise RuntimeError(msg)
        for host, port, _ in self.hosts:
            try:
                connection = await self._connect(host, port)
            except (OSError, KafkaError, TimeoutError):
                continue
            try:
                metadata = await connection.send(MetadataRequest([]))
            except (KafkaError, TimeoutError):
                connection.close()
                continue
            except BaseException:
                connection.close()
                raise
            self.cluster.update_metadata(metadata)
            if not self.cluster.brokers():
                self._conns[("bootstrap", ConnectionGroup.DEFAULT)] = connection
            else:
                connection.close()
            break
        else:
            msg = "Unable to connect to permitted Kafka bootstrap brokers"
            raise KafkaConnectionError(msg)
        if self._sync_task is None:
            self._sync_task = asyncio.create_task(self._md_synchronizer())  # type: ignore[no-untyped-call]

    async def _get_conn(
        self,
        node_id: int | str,
        *,
        group: ConnectionGroup = ConnectionGroup.DEFAULT,
        no_hint: bool = False,  # noqa: ARG002 - upstream signature
    ) -> AIOKafkaConnection | None:
        """Protect every new broker/coordinator socket, including reconnections."""
        key = (node_id, group)
        if key in self._conns:
            connection = self._conns[key]
            if connection.connected():
                return connection  # type: ignore[no-any-return]
            del self._conns[key]
        try:
            broker = self.cluster.broker_metadata(node_id)
            if broker is None:
                msg = "Kafka broker metadata is unavailable"
                raise StaleMetadata(msg)
            async with self._get_conn_lock:
                if key not in self._conns:
                    self._conns[key] = await self._connect(broker.host, broker.port)
        except (OSError, KafkaError, TimeoutError):
            self.force_metadata_update()  # type: ignore[no-untyped-call]
            return None
        return self._conns[key]  # type: ignore[no-any-return]
