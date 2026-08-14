"""identity_providers API endpoints."""

from __future__ import annotations

import importlib
from typing import Any, Protocol, cast

from ...client import AuthenticatedClient
from ...types import Response


class _EndpointModule(Protocol):
    def sync_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...

    async def asyncio_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...


class IdentityProvidersApi:
    """Registry for identity_providers API endpoints."""

    def __init__(self, client: AuthenticatedClient) -> None:
        self._client = client

    def _load_endpoint_module(self, module_name: str) -> _EndpointModule:
        return cast(_EndpointModule, importlib.import_module(f"{__name__}.{module_name}"))

    def list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_identity_providers")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_identity_providers")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_identity_provider")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_identity_provider")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_identity_provider")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_identity_provider")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def delete(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_identity_provider")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_delete(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_identity_provider")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def update(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_identity_provider")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_update(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_identity_provider")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def setup_aap_oidc_provider(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("setup_aap_oidc_provider")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_setup_aap_oidc_provider(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("setup_aap_oidc_provider")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def test(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("test_identity_provider")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_test(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("test_identity_provider")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)
