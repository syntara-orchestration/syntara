"""Kafka service boundaries must not resolve DNS before the adapter deadline."""

import asyncio
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.integrations.adapters.protocol import HealthCheckErrorType
from syntara.integrations.lib.kafka_connection import approved_broker_addresses
from syntara.integrations.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationStatus,
    IntegrationTestConnection,
    IntegrationType,
    IntegrationUpdate,
)
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.integrations.services.integration_service import IntegrationService

pytestmark = [pytest.mark.asyncio, pytest.mark.ssrf_enforced]


def _configuration() -> KafkaConfiguration:
    return KafkaConfiguration(bootstrap_servers=["broker.example.com:9093"], security_protocol="SSL")


@pytest.mark.parametrize("saved", [False, True], ids=["discover", "saved-validation"])
@pytest.mark.parametrize("address", ["8.8.8.8", "169.254.169.254"], ids=["slow-public-dns", "unsafe-dns"])
async def test_kafka_dns_obeys_adapter_deadline(
    test_db_session: AsyncSession, test_user: User, *, saved: bool, address: str
) -> None:
    """Two 0.6s lookups share the 1s budget and leave the event loop responsive."""
    service = IntegrationService(test_db_session, test_user)
    integration = Integration(
        name=f"dns-{uuid4()}",
        integration_type=IntegrationType.KAFKA,
        configuration=_configuration(),
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    if saved:
        test_db_session.add(integration)
        await test_db_session.commit()
    dns_calls = 0

    def slow_dns(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        nonlocal dns_calls
        dns_calls += 1
        if address == "8.8.8.8":
            time.sleep(0.6)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 9093))]

    async def bootstrap() -> None:
        await approved_broker_addresses("broker.example.com", 9093)

    loop = asyncio.get_running_loop()
    timer_elapsed: list[float] = []
    start = loop.time()
    timer = loop.call_later(0.05, lambda: timer_elapsed.append(loop.time() - start))
    try:
        with (
            patch("socket.getaddrinfo", side_effect=slow_dns),
            patch(
                "syntara.integrations.lib.kafka_connection.get_settings",
                return_value=SimpleNamespace(integration_url_allowed_hosts=[]),
            ),
            patch(
                "syntara.integrations.services.integration_service.get_runtime_settings",
                return_value=SimpleNamespace(get=AsyncMock(return_value=1)),
            ),
            patch("syntara.integrations.adapters.kafka.KafkaHealthClient.bootstrap", side_effect=bootstrap),
        ):
            result = (
                await service.validate_integration(integration.id)
                if saved
                else await service.discover(
                    IntegrationTestConnection(integration_type=IntegrationType.KAFKA, configuration=_configuration())
                )
            )
        assert not result.success
        if address == "8.8.8.8":
            assert result.error_type == HealthCheckErrorType.TIMEOUT
            assert dns_calls == 2
            assert timer_elapsed
            assert timer_elapsed[0] < 0.3
        else:
            assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
            assert dns_calls == 1
        assert loop.time() - start < 1.5
        if saved:
            await test_db_session.refresh(integration)
            assert integration.validation_status == IntegrationStatus.ERROR
    finally:
        timer.cancel()
        # Let the cancelled executor lookup finish before patches/fixtures tear down.
        await asyncio.sleep(0.3)


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_kafka_write_dns_is_off_loop_and_rejects_unsafe_destinations(
    test_db_session: AsyncSession, test_user: User, operation: str
) -> None:
    """Create and update keep DNS-based rejection without blocking the loop."""
    service = IntegrationService(test_db_session, test_user)
    integration = Integration(
        name=f"dns-write-{uuid4()}",
        integration_type=IntegrationType.KAFKA,
        configuration=_configuration(),
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    if operation == "update":
        test_db_session.add(integration)
        await test_db_session.commit()
    main_thread = threading.get_ident()
    dns_threads: list[int] = []

    def unsafe_dns(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        dns_threads.append(threading.get_ident())
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("169.254.169.254", 9093))]

    with patch("socket.getaddrinfo", side_effect=unsafe_dns):
        with pytest.raises(SafeValueError, match="bootstrap_servers must not resolve"):
            if operation == "create":
                await service.create_integration(
                    IntegrationCreate(
                        name=integration.name, integration_type=IntegrationType.KAFKA, configuration=_configuration()
                    )
                )
            else:
                await service.update_integration(integration.id, IntegrationUpdate(configuration=_configuration()))
    assert dns_threads
    assert all(thread != main_thread for thread in dns_threads)
