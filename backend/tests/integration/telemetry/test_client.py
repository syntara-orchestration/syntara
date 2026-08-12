"""Integration tests for TelemetryClientRegistry and initialize_telemetry().

Tests cover:
- US2: Registry stores anonymous_id after initialization and passes it to client.track()
- US3: entitlement_id is always present in event properties
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.telemetry.client import TelemetryClientRegistry, initialize_telemetry
from syntara.telemetry.events.base import BaseTelemetryEvent

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager


class _DummyEvent(BaseTelemetryEvent):
    """Minimal event for testing send_event()."""

    entitlement_id: str = ""
    value: str = "test"

    def to_segment_event(self) -> dict[str, object]:
        return {"event": "dummy_event", "properties": {"value": self.value}}


class TestRegistryAnonymousId:
    """US2: Verify anonymous_id flows from registry to Segment track calls."""

    def test_anonymous_id_stored_after_initialize(self) -> None:
        """Registry should store the anonymous_id passed at initialization."""
        registry = TelemetryClientRegistry()
        registry.initialize(
            write_key="test-key",
            anonymous_id="abc123def456",
        )
        assert registry.anonymous_id == "abc123def456"

    def test_send_event_passes_anonymous_id(self) -> None:
        """send_event() should pass anonymous_id to client.track()."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._anonymous_id = "anon-id-xyz"

        event = _DummyEvent()
        registry.send_event(event)

        mock_client.track.assert_called_once()
        call_kwargs = mock_client.track.call_args.kwargs
        assert call_kwargs["anonymous_id"] == "anon-id-xyz"


class TestEntitlementIdInProperties:
    """US3: Verify entitlement_id is always included in event properties."""

    def test_entitlement_id_in_properties_when_configured(self) -> None:
        """When entitlement_id is set, it should appear in event properties."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = "ent-id-123"
        registry._anonymous_id = "anon-id"

        event = _DummyEvent()
        registry.send_event(event)

        call_kwargs = mock_client.track.call_args.kwargs
        assert call_kwargs["properties"]["entitlement_id"] == "ent-id-123"

    def test_entitlement_id_empty_string_when_not_configured(self) -> None:
        """When entitlement_id is not configured, it should be empty string in properties."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = ""
        registry._anonymous_id = "anon-id"

        event = _DummyEvent()
        registry.send_event(event)

        call_kwargs = mock_client.track.call_args.kwargs
        assert call_kwargs["properties"]["entitlement_id"] == ""


class TestInitializeTelemetry:
    """US2: Verify initialize_telemetry() derives anonymous_id from installation ID and DB settings."""

    @pytest.mark.asyncio
    async def test_initialize_sets_anonymous_id(
        self,
        test_db_engine: AsyncEngine,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """initialize_telemetry() should derive a 64-char anonymous_id."""
        mock_registry = MagicMock(spec=TelemetryClientRegistry)
        mock_registry.is_initialized.return_value = False

        session_factory = async_sessionmaker(
            test_db_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        with (
            patch("syntara.telemetry.client._get_telemetry_registry", return_value=mock_registry),
            override_settings(
                segment_write_key=SecretStr("test-write-key"),
                entitlement_id="test-ent-id",
                db_host="db.example.com",
                db_name="nexus_prod",
            ),
        ):
            result = await initialize_telemetry(session_factory=session_factory)

        assert result is True
        mock_registry.initialize.assert_called_once()
        call_kwargs = mock_registry.initialize.call_args.kwargs
        # anonymous_id should be a 64-char hex string (SHA-256)
        assert len(call_kwargs["anonymous_id"]) == 64
        assert call_kwargs["entitlement_id"] == "test-ent-id"
