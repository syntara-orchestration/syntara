"""files API endpoints."""

from __future__ import annotations

import importlib
from typing import Any, Protocol, cast

from ...client import AuthenticatedClient
from ...types import Response


class _EndpointModule(Protocol):
    def sync_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...

    async def asyncio_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...


class FilesApi:
    """Registry for files API endpoints."""

    def __init__(self, client: AuthenticatedClient) -> None:
        self._client = client

    def _load_endpoint_module(self, module_name: str) -> _EndpointModule:
        return cast(_EndpointModule, importlib.import_module(f"{__name__}.{module_name}"))

    def upload(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("upload_files")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_upload(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("upload_files")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get_storage_status(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_file_storage_status")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get_storage_status(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_file_storage_status")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get_metadata(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_files_metadata")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get_metadata(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_files_metadata")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get_details(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_file_details")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get_details(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_file_details")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def delete(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_file")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_delete(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_file")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def download(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("download_file")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_download(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("download_file")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)
