"""executions API endpoints."""

from __future__ import annotations

import importlib
from typing import Any, Protocol, cast

from ...client import AuthenticatedClient
from ...types import Response


class _EndpointModule(Protocol):
    def sync_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...

    async def asyncio_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...


class ExecutionsApi:
    """Registry for executions API endpoints."""

    def __init__(self, client: AuthenticatedClient) -> None:
        self._client = client

    def _load_endpoint_module(self, module_name: str) -> _EndpointModule:
        return cast(_EndpointModule, importlib.import_module(f"{__name__}.{module_name}"))

    def list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_executions")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_executions")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_execution")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_execution")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_execution")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_execution")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def cancel(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("cancel_execution")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_cancel(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("cancel_execution")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def retry(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("retry_execution")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_retry(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("retry_execution")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def retry_from_failure_preview(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("retry_from_failure_preview")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_retry_from_failure_preview(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("retry_from_failure_preview")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def retry_from_failure(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("retry_from_failure")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_retry_from_failure(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("retry_from_failure")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_activities(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_execution_activities")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_activities(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_execution_activities")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def signal_activity(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("signal_activity")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_signal_activity(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("signal_activity")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)
