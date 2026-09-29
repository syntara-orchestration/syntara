"""form_prompts API endpoints."""

from __future__ import annotations

import importlib
from typing import Any, Protocol, cast

from ...client import AuthenticatedClient
from ...types import Response


class _EndpointModule(Protocol):
    def sync_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...

    async def asyncio_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...


class FormPromptsApi:
    """Registry for form_prompts API endpoints."""

    def __init__(self, client: AuthenticatedClient) -> None:
        self._client = client

    def _load_endpoint_module(self, module_name: str) -> _EndpointModule:
        return cast(_EndpointModule, importlib.import_module(f"{__name__}.{module_name}"))

    def list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_form_prompts")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_form_prompts")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_form_prompt")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_form_prompt")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def batch_update(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("batch_update_form_prompts")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_batch_update(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("batch_update_form_prompts")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_form_prompt")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_form_prompt")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def submit(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("submit_form_prompt")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_submit(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("submit_form_prompt")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)
