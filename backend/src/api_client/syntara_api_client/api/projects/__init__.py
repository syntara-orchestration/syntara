"""projects API endpoints."""

from __future__ import annotations

import importlib
from typing import Any, Protocol, cast

from ...client import AuthenticatedClient
from ...types import Response


class _EndpointModule(Protocol):
    def sync_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...

    async def asyncio_detailed(self, *, client: AuthenticatedClient, **kwargs: Any) -> Response[Any]: ...


class ProjectsApi:
    """Registry for projects API endpoints."""

    def __init__(self, client: AuthenticatedClient) -> None:
        self._client = client

    def _load_endpoint_module(self, module_name: str) -> _EndpointModule:
        return cast(_EndpointModule, importlib.import_module(f"{__name__}.{module_name}"))

    def list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_projects")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_projects")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_create(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def replace(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("replace_project")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_replace(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("replace_project")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def delete(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_delete(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def update(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_project")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_update(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_project")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_workflows(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_workflows")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_workflows(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_workflows")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_approvals(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_approvals")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_approvals(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_approvals")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_role_assignments(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_role_assignments")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_role_assignments(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_role_assignments")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def create_role_assignment(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project_role_assignment")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_create_role_assignment(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project_role_assignment")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def delete_role_assignment(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project_role_assignment")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_delete_role_assignment(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project_role_assignment")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_roles(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_roles")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_roles(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_roles")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def create_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project_role")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_create_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project_role")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project_role")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project_role")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def replace_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("replace_project_role")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_replace_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("replace_project_role")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def delete_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project_role")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_delete_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project_role")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def update_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_project_role")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_update_role(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_project_role")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_policies(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_policies")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_policies(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_policies")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def create_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project_policy")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_create_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project_policy")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project_policy")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project_policy")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def replace_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("replace_project_policy")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_replace_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("replace_project_policy")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def delete_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project_policy")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_delete_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project_policy")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def update_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_project_policy")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_update_policy(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_project_policy")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def list_credentials(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_credentials")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_list_credentials(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("list_project_credentials")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def create_credential(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project_credential")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_create_credential(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("create_project_credential")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get_credential(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project_credential")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get_credential(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project_credential")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def delete_credential(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project_credential")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_delete_credential(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("delete_project_credential")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def update_credential(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_project_credential")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_update_credential(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("update_project_credential")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)

    def get_credential_workflows(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project_credential_workflows")
        return endpoint_module.sync_detailed(client=self._client, **kwargs)

    async def async_get_credential_workflows(self, **kwargs: Any) -> Response[Any]:
        endpoint_module = self._load_endpoint_module("get_project_credential_workflows")
        return await endpoint_module.asyncio_detailed(client=self._client, **kwargs)
