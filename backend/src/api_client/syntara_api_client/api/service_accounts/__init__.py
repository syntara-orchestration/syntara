"""service_accounts API endpoints."""

from __future__ import annotations

import importlib
from typing import Any, Protocol, cast

from ...client import AuthenticatedClient
from ...types import Response


class _EndpointModule(Protocol):
    def sync_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...

    async def asyncio_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...


class ServiceAccountsApi:
    """Registry for service_accounts API endpoints."""

    def __init__(self, client: AuthenticatedClient) -> None:
        self._client = client

    def _load_endpoint_module(self, module_name: str) -> _EndpointModule:
        return cast(_EndpointModule, importlib.import_module(f"{__name__}.{module_name}"))

    def list_directory(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_service_accounts_directory")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_directory(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_service_accounts_directory")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_service_accounts")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_service_accounts")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_service_account")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_service_account")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_service_account")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_service_account")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def delete(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_service_account")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_delete(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_service_account")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def update(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_service_account")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_update(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_service_account")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def disable(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("disable_service_account")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_disable(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("disable_service_account")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def enable(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("enable_service_account")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_enable(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("enable_service_account")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)
