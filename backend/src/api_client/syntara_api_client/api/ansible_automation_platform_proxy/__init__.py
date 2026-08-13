"""ansible_automation_platform_proxy API endpoints."""

from __future__ import annotations

import importlib
from typing import Any, Protocol, cast

from ...client import AuthenticatedClient
from ...types import Response


class _EndpointModule(Protocol):
    def sync_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...

    async def asyncio_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...


class AnsibleAutomationPlatformProxyApi:
    """Registry for ansible_automation_platform_proxy API endpoints."""

    def __init__(self, client: AuthenticatedClient) -> None:
        self._client = client

    def _load_endpoint_module(self, module_name: str) -> _EndpointModule:
        return cast(_EndpointModule, importlib.import_module(f"{__name__}.{module_name}"))

    def list_aap_organizations(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_organizations")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_aap_organizations(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_organizations")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_aap_job_templates(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_job_templates")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_aap_job_templates(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_job_templates")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get_aap_job_template(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_aap_job_template")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get_aap_job_template(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_aap_job_template")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_aap_workflow_job_templates(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_workflow_job_templates")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_aap_workflow_job_templates(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_workflow_job_templates")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get_aap_workflow_job_template(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_aap_workflow_job_template")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get_aap_workflow_job_template(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_aap_workflow_job_template")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_aap_inventories(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_inventories")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_aap_inventories(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_inventories")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_aap_execution_environments(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_execution_environments")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_aap_execution_environments(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_execution_environments")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_aap_credentials(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_credentials")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_aap_credentials(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_credentials")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_aap_instance_groups(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_instance_groups")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_aap_instance_groups(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_instance_groups")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_aap_labels(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_labels")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_aap_labels(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_aap_labels")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)
