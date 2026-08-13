"""Segment telemetry client registry.

Provides a singleton registry for the Segment Analytics client following
the WorkerRegistry pattern used in temporal_worker.py.
"""

from __future__ import annotations

import hashlib
import uuid
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import segment.analytics as segment_analytics  # type: ignore[import-untyped]
import structlog
from sqlmodel import select

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models.installation import Installation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.telemetry.events.base import BaseTelemetryEvent

logger = structlog.stdlib.get_logger(__name__)


async def get_installation(session: AsyncSession) -> Installation:
    """Read the installation record from the database.

    The installation row is seeded by an Alembic migration and must always
    exist.

    Args:
        session: Async database session.

    Returns:
        The Installation singleton.

    Raises:
        RuntimeError: If the installation row is missing.

    """
    result = await session.exec(select(Installation))
    installation = result.first()
    if installation is None:
        msg = "Installation table is empty — the Alembic migration that seeds the row must run first"
        raise RuntimeError(msg)
    return installation


def derive_anonymous_id(installation_id: uuid.UUID, db_host: str, db_name: str) -> str:
    """Derive a stable anonymous identifier for telemetry.

    Combines the installation ID with database connection coordinates and
    produces a SHA-256 hex digest.  This ensures distinct environments
    (e.g. production vs. a restored snapshot) yield different identifiers.

    Args:
        installation_id: The installation UUID from the database.
        db_host: Database host from settings.
        db_name: Database name from settings.

    Returns:
        A 64-character lowercase hex string.

    """
    raw = f"{installation_id}:{db_host}:{db_name}"
    return hashlib.sha256(raw.encode()).hexdigest()


class TelemetryClientRegistry:
    """Registry for managing Segment Analytics client lifecycle without global variables."""

    def __init__(self) -> None:
        """Initialize the registry."""
        self._client: segment_analytics.Client | None = None
        self._entitlement_id: str = ""
        self._anonymous_id: str = ""
        self._installation_salt: str = ""

    def initialize(
        self,
        write_key: str,
        host: str = "https://api.segment.io",
        entitlement_id: str = "",
        anonymous_id: str = "",
        installation_salt: str = "",
        max_retries: int = 10,
        timeout: int = 30,
    ) -> None:
        """Initialize the Segment client.

        Should be called once at Temporal Worker startup.

        Args:
            write_key: Segment write API key.
            host: Segment API endpoint URL.
            entitlement_id: Optional entitlement identifier included in event properties.
            anonymous_id: Derived telemetry identifier used as Segment ``anonymousId``.
            installation_salt: Per-installation salt (installation UUID) for HMAC-based
                user ID hashing.
            max_retries: Maximum number of retries for batch uploads.
            timeout: HTTP timeout in seconds for batch uploads.

        """
        if self._client is not None:
            logger.warning("TelemetryClientRegistry already initialized")
            return

        self._entitlement_id = entitlement_id
        self._anonymous_id = anonymous_id
        self._installation_salt = installation_salt
        self._client = segment_analytics.Client(
            write_key=write_key,
            host=host,
            gzip=True,
            max_queue_size=20000,
            max_retries=max_retries,
            timeout=timeout,
            upload_interval=0.5,
            upload_size=100,
            on_error=self._error_handler,
        )
        logger.info(
            "Telemetry client initialized",
            anonymous_id=anonymous_id,
            entitlement_id=entitlement_id,
        )

    def get_client(self) -> segment_analytics.Client:
        """Get the initialized Segment client instance.

        Returns:
            The Segment Analytics client.

        Raises:
            RuntimeError: If the registry has not been initialized.

        """
        if self._client is None:
            msg = "TelemetryClientRegistry not initialized. Call initialize() first."
            raise RuntimeError(msg)
        return self._client

    def send_event(self, event: BaseTelemetryEvent) -> None:
        """Send a telemetry event to Segment (fire-and-forget).

        The derived ``anonymous_id`` is used as the Segment ``anonymousId``.
        The ``entitlement_id`` is always included in event properties
        (empty string when not configured).

        If the event does not carry a ``request_id``, the current value of
        :data:`~syntara.audit.emitter.request_id_context_var` is injected
        automatically so that events emitted during an HTTP request are
        correlated without explicit parameter threading.

        Args:
            event: Telemetry event to send.

        """
        try:
            if not self.is_initialized():
                return
            client = self.get_client()
            segment_event = event.to_segment_event()

            logger.info(
                "Sending telemetry event",
                event_name=segment_event.get("event"),
            )

            raw_props = segment_event.get("properties", {})
            properties: dict[str, object] = dict(raw_props) if isinstance(raw_props, dict) else {}
            properties["entitlement_id"] = self._entitlement_id

            # Inject request_id from ContextVar if the event doesn't have one
            if not properties.get("request_id"):
                from syntara.audit.emitter import request_id_context_var  # noqa: PLC0415

                ctx_request_id = request_id_context_var.get()
                if ctx_request_id is not None:
                    properties["request_id"] = str(ctx_request_id)
            elif isinstance(properties.get("request_id"), uuid.UUID):
                properties["request_id"] = str(properties["request_id"])

            raw_context = segment_event.get("context", {})
            context: dict[str, object] = dict(raw_context) if isinstance(raw_context, dict) else {}

            client.track(
                anonymous_id=self._anonymous_id,
                event=segment_event["event"],
                properties=properties,
                context=context,
            )
        except Exception:
            logger.exception("Failed to send telemetry event (fire-and-forget)")

    def flush(self) -> None:
        """Flush pending events to Segment.

        Should be called at Temporal Worker shutdown.
        """
        if self._client:
            logger.info("Flushing pending telemetry events")
            self._client.flush()

    def is_initialized(self) -> bool:
        """Check if the registry has been initialized.

        Returns:
            True if the Segment client has been initialized.

        """
        return self._client is not None

    @property
    def anonymous_id(self) -> str:
        """Get the derived anonymous identifier.

        Returns:
            The derived telemetry identifier (SHA-256 hex digest).

        """
        return self._anonymous_id

    @property
    def entitlement_id(self) -> str:
        """Get the configured entitlement_id.

        Returns:
            The optional entitlement identifier.

        """
        return self._entitlement_id

    @property
    def installation_salt(self) -> str:
        """Get the per-installation salt (installation UUID).

        Used as the HMAC key for anonymizing user IDs in telemetry events.

        Returns:
            The installation UUID string used as the HMAC salt.

        """
        return self._installation_salt

    @staticmethod
    def _error_handler(error: Exception, items: list[Any]) -> None:
        """Handle Segment SDK errors (fire-and-forget, log only).

        Args:
            error: The error that occurred.
            items: The items that failed to send.

        """
        logger.warning(
            "Segment SDK error (fire-and-forget)",
            error=str(error),
            item_count=len(items),
        )


@lru_cache(maxsize=1)
def _get_telemetry_registry() -> TelemetryClientRegistry:
    """Get the singleton TelemetryClientRegistry instance.

    lru_cache provides thread-safe singleton without global mutable state.
    The registry itself manages the mutable client reference.

    Returns:
        The shared TelemetryClientRegistry instance.

    """
    return TelemetryClientRegistry()


def get_telemetry_registry() -> TelemetryClientRegistry:
    """Get the telemetry client registry.

    Returns:
        The TelemetryClientRegistry singleton.

    """
    return _get_telemetry_registry()


async def initialize_telemetry(session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal) -> bool:
    """Initialize the telemetry client from application settings.

    Reads the installation ID from the database, derives the anonymous
    telemetry identifier, and initializes the singleton registry.
    Safe to call multiple times — subsequent calls are no-ops.

    Returns:
        True if telemetry was initialized, False if disabled (no write key).

    """
    settings = get_settings()
    segment_key = settings.segment_write_key.get_secret_value()
    if not segment_key:
        logger.info("Telemetry disabled: no Segment write key configured")
        return False

    # Read installation record from database
    async with session_factory() as session:
        installation = await get_installation(session)

    anonymous_id = derive_anonymous_id(installation.id, settings.db_host, settings.db_name)

    registry = get_telemetry_registry()
    registry.initialize(
        write_key=segment_key,
        host=str(settings.segment_endpoint),
        entitlement_id=settings.entitlement_id,
        anonymous_id=anonymous_id,
        installation_salt=str(installation.salt),
        max_retries=settings.segment_max_retries,
        timeout=settings.segment_timeout,
    )
    return True


def flush_telemetry() -> None:
    """Flush pending telemetry events.

    Should be called during shutdown to ensure all events are sent.
    """
    registry = get_telemetry_registry()
    if registry.is_initialized():
        registry.flush()
