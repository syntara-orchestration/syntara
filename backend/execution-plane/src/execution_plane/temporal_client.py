"""Temporal client — settings, connection, and async-completion callback.

BOUNDARY CROSSING — see docs/execution-plane/integration.md.
The EP worker uses Temporal's async-activity-completion API to resume the
suspended Syntara activity once a script finishes. This module is the only
place in execution_plane that imports from temporalio; worker.py calls only
send_temporal_callback and has no other knowledge of Temporal.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import structlog
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode, TLSConfig

from execution_plane.models.work_item import WorkItem, WorkItemStatus

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class _ClientCache:
    client: Client | None = None


_client_cache = _ClientCache()


class TemporalSettings(BaseSettings):
    """Temporal connection and optional mutual TLS settings."""

    model_config = SettingsConfigDict(extra="ignore")

    temporal_address: str = Field(default="localhost:7233", validation_alias="APP_TEMPORAL_ADDRESS")
    temporal_namespace: str = Field(default="default", validation_alias="APP_TEMPORAL_NAMESPACE")

    s2s_tls_enabled: bool = Field(default=False, validation_alias="APP_S2S_TLS_ENABLED")
    s2s_tls_ca_cert_path: str | None = Field(default=None, validation_alias="APP_S2S_TLS_CA_CERT_PATH")
    s2s_tls_cert_path: str | None = Field(default=None, validation_alias="APP_S2S_TLS_CERT_PATH")
    s2s_tls_key_path: str | None = Field(default=None, validation_alias="APP_S2S_TLS_KEY_PATH")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tls_config(self) -> TLSConfig | None:
        """Build mutual TLS configuration when all certificate paths are set."""
        if not self.s2s_tls_enabled:
            return None
        if not (self.s2s_tls_ca_cert_path and self.s2s_tls_cert_path and self.s2s_tls_key_path):
            return None
        return TLSConfig(
            server_root_ca_cert=Path(self.s2s_tls_ca_cert_path).read_bytes(),
            client_cert=Path(self.s2s_tls_cert_path).read_bytes(),
            client_private_key=Path(self.s2s_tls_key_path).read_bytes(),
        )


@lru_cache
def get_temporal_settings() -> TemporalSettings:
    """Load and cache Temporal settings from the environment."""
    return TemporalSettings()


async def _get_client() -> Client:
    if _client_cache.client is None:
        settings = get_temporal_settings()
        tls = settings.tls_config
        _client_cache.client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
            tls=tls,
        )
        logger.info(
            "Connected to Temporal",
            address=settings.temporal_address,
            namespace=settings.temporal_namespace,
            tls_enabled=tls is not None,
        )
    return _client_cache.client


async def send_temporal_callback(item: WorkItem, *, client: Client | None = None) -> bool:
    """Resume the suspended Syntara activity with the script result.

    Returns True if the callback was delivered (or the token was already consumed),
    False if a retryable RPC error occurred — caller should not mark_signal_delivered.
    """
    wi_id = str(item.id)
    if client is None:
        client = await _get_client()
    task_token = base64.b64decode(item.activity_handle)
    handle = client.get_async_activity_handle(task_token=task_token)

    try:
        if item.status == WorkItemStatus.COMPLETED:
            await handle.complete(item.result or {})
        else:
            result = item.result or {}
            error_msg = result.get("error", "Script execution failed")
            error_type = result.get("error_type", "ScriptExecutionError")
            await handle.fail(ApplicationError(error_msg, type=error_type, non_retryable=True))
    except RPCError as e:
        if e.status == RPCStatusCode.NOT_FOUND:
            logger.info("Temporal activity already completed, treating as delivered", work_item_id=wi_id)
            return True
        logger.warning(
            "Failed to signal Temporal, will retry on next recovery pass",
            work_item_id=wi_id,
            error=str(e),
        )
        return False

    logger.info("Temporal callback delivered", work_item_id=wi_id, status=item.status)
    return True
