"""filtering API endpoints."""

from __future__ import annotations

import importlib
from typing import Any, Protocol, cast

from ...client import AuthenticatedClient
from ...types import Response


class _EndpointModule(Protocol):
    def sync_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...

    async def asyncio_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...


class FilteringApi:
    """Registry for filtering API endpoints."""

    def __init__(self, client: AuthenticatedClient) -> None:
        self._client = client

    def _load_endpoint_module(self, module_name: str) -> _EndpointModule:
        return cast(_EndpointModule, importlib.import_module(f"{__name__}.{module_name}"))

    def test_cel_filter(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("test_cel_filter")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_test_cel_filter(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("test_cel_filter")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)
