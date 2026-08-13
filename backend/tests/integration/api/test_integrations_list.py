"""Contract tests for GET /api/v1/integrations."""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.models import User
from syntara.integrations.models.integration import IntegrationStatus, IntegrationType
from tests.integration.api.conftest import make_admin, make_project_user, mcp_payload
from tests.integration.helpers.integration import IntegrationFactory

BASE_URL = "/api/v1/integrations"


class TestIntegrationsList:
    """Contract tests for GET /api/v1/integrations."""

    async def test_list_returns_200_with_resources_and_count(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """List endpoint returns 200 with resources list and pagination fields."""
        response = await auth_client.get(BASE_URL)
        assert response.status_code == 200
        data = response.json()
        assert "resources" in data
        assert isinstance(data["resources"], list)
        assert "next" in data
        assert "prev" in data

    async def test_list_returns_created_integrations(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Integrations created in the DB appear in list results."""
        names = [f"list-{uuid4().hex[:8]}" for _ in range(3)]
        for name in names:
            await integration_factory.create(name=name)
        await test_db_session.commit()

        response = await auth_client.get(BASE_URL)
        assert response.status_code == 200
        data = response.json()
        returned_names = {r["name"] for r in data["resources"]}
        for name in names:
            assert name in returned_names

    async def test_list_filter_by_integration_type(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Filter by integration_type returns only matching integrations."""
        await integration_factory.create(integration_type=IntegrationType.MCP_SERVER)
        await integration_factory.create(integration_type=IntegrationType.LLM_PROVIDER)
        await test_db_session.commit()

        response = await auth_client.get(BASE_URL, params={"integration_type[eq]": "llm_provider"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["resources"]) >= 1
        for resource in data["resources"]:
            assert resource["integration_type"] == "llm_provider"

    async def test_list_filter_by_enabled(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Filter by enabled=false returns only disabled integrations."""
        enabled_name = f"enabled-{uuid4().hex[:8]}"
        disabled_name = f"disabled-{uuid4().hex[:8]}"
        await integration_factory.create(name=enabled_name, enabled=True)
        await integration_factory.create(name=disabled_name, enabled=False)
        await test_db_session.commit()

        response = await auth_client.get(BASE_URL, params={"enabled[eq]": "false"})
        assert response.status_code == 200
        data = response.json()
        returned_names = {r["name"] for r in data["resources"]}
        assert len(data["resources"]) >= 1
        assert disabled_name in returned_names
        assert enabled_name not in returned_names
        for resource in data["resources"]:
            assert resource["enabled"] is False

    async def test_list_pagination_limit(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Limit parameter restricts number of returned resources."""
        await integration_factory.create_many(5)
        await test_db_session.commit()

        response = await auth_client.get(BASE_URL, params={"limit": "2"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["resources"]) == 2

    async def test_list_pagination_cursor(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Cursor pagination returns non-overlapping pages."""
        await integration_factory.create_many(4)
        await test_db_session.commit()

        first = await auth_client.get(BASE_URL, params={"limit": "2"})
        assert first.status_code == 200
        first_data = first.json()
        assert len(first_data["resources"]) == 2

        cursor = first_data.get("next")
        assert cursor is not None, "Expected a next cursor with 4 records and limit=2"

        second = await auth_client.get(BASE_URL, params={"limit": "2", "cursor": cursor})
        assert second.status_code == 200
        second_data = second.json()

        first_ids = {r["id"] for r in first_data["resources"]}
        second_ids = {r["id"] for r in second_data["resources"]}
        assert first_ids.isdisjoint(second_ids)

    async def test_list_excludes_deleted_integrations(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Deleted integrations do not appear in list results."""
        name = f"gone-{uuid4().hex[:8]}"
        integration = await integration_factory.create(name=name)
        await test_db_session.commit()

        await auth_client.delete(f"{BASE_URL}/{integration.id}")

        response = await auth_client.get(BASE_URL)
        assert response.status_code == 200
        returned_names = {r["name"] for r in response.json()["resources"]}
        assert name not in returned_names

    async def test_list_invalid_limit_returns_422(self, auth_client: AsyncClient) -> None:
        """Invalid limit value returns 422."""
        response = await auth_client.get(BASE_URL, params={"limit": "not-a-number"})
        assert response.status_code == 422

    async def test_list_requires_authentication(self, base_client: AsyncClient) -> None:
        """GET list requires authentication."""
        response = await base_client.get(BASE_URL)
        assert response.status_code == 401

    async def test_list_include_total(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """include_total=true includes a total count in the response."""
        await integration_factory.create_many(3)
        await test_db_session.commit()

        response = await auth_client.get(BASE_URL, params={"include_total": "true"})
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert isinstance(data["total"], int)
        assert data["total"] >= 3

    async def test_list_filter_by_validation_status(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Filter by validation_status returns only matching integrations."""
        available = await integration_factory.create(name=f"avail-{uuid4().hex[:8]}")
        available.validation_status = IntegrationStatus.AVAILABLE
        error = await integration_factory.create(name=f"err-{uuid4().hex[:8]}")
        error.validation_status = IntegrationStatus.ERROR
        unknown = await integration_factory.create(name=f"unk-{uuid4().hex[:8]}")
        unknown.validation_status = IntegrationStatus.UNKNOWN
        await test_db_session.commit()

        response = await auth_client.get(BASE_URL, params={"validation_status": "available"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["resources"]) >= 1
        returned_names = {r["name"] for r in data["resources"]}
        assert available.name in returned_names
        assert error.name not in returned_names
        for resource in data["resources"]:
            assert resource["validation_status"] == "available"

        response_err = await auth_client.get(BASE_URL, params={"validation_status": "error"})
        assert response_err.status_code == 200
        err_data = response_err.json()
        err_names = {r["name"] for r in err_data["resources"]}
        assert error.name in err_names
        assert available.name not in err_names

    async def test_list_sort_by_name(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Sort parameter orders results correctly."""
        prefix = f"sort-{uuid4().hex[:6]}"
        await integration_factory.create(name=f"{prefix}-charlie")
        await integration_factory.create(name=f"{prefix}-alpha")
        await integration_factory.create(name=f"{prefix}-bravo")
        await test_db_session.commit()

        asc_resp = await auth_client.get(BASE_URL, params={"sort": "name", "limit": "100"})
        assert asc_resp.status_code == 200
        asc_names = [r["name"] for r in asc_resp.json()["resources"] if r["name"].startswith(prefix)]
        assert asc_names == sorted(asc_names)

        desc_resp = await auth_client.get(BASE_URL, params={"sort": "-name", "limit": "100"})
        assert desc_resp.status_code == 200
        desc_names = [r["name"] for r in desc_resp.json()["resources"] if r["name"].startswith(prefix)]
        assert desc_names == sorted(desc_names, reverse=True)

    async def test_list_combined_filters(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Multiple filters applied simultaneously narrow results correctly."""
        mcp_enabled = await integration_factory.create(
            name=f"combo-mcp-on-{uuid4().hex[:8]}",
            integration_type=IntegrationType.MCP_SERVER,
            enabled=True,
        )
        mcp_disabled = await integration_factory.create(
            name=f"combo-mcp-off-{uuid4().hex[:8]}",
            integration_type=IntegrationType.MCP_SERVER,
            enabled=False,
        )
        llm_enabled = await integration_factory.create(
            name=f"combo-llm-on-{uuid4().hex[:8]}",
            integration_type=IntegrationType.LLM_PROVIDER,
            enabled=True,
        )
        await test_db_session.commit()

        response = await auth_client.get(
            BASE_URL,
            params={
                "integration_type[eq]": "mcp_server",
                "enabled[eq]": "true",
            },
        )
        assert response.status_code == 200
        data = response.json()
        returned_names = {r["name"] for r in data["resources"]}

        assert mcp_enabled.name in returned_names
        assert mcp_disabled.name not in returned_names
        assert llm_enabled.name not in returned_names

        for resource in data["resources"]:
            assert resource["integration_type"] == "mcp_server"
            assert resource["enabled"] is True


async def _create_project(session: AsyncSession, name: str | None = None) -> Project:
    project = Project(name=name or f"proj-{uuid4().hex[:8]}", description="Test project")
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


class TestIntegrationsListProjectFilter:
    """Tests for project_id query parameter on GET /api/v1/integrations."""

    async def test_project_id_returns_global_and_assigned(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """project_id filter returns global integrations and those assigned to the project."""
        admin = await user_factory(username=f"pf-adm-{uuid4().hex[:6]}", email=f"pf-adm-{uuid4().hex[:6]}@t.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        project = await _create_project(test_db_session)

        global_resp = await auth_client.post(BASE_URL, json=mcp_payload(name=f"global-{uuid4().hex[:8]}"))
        assert global_resp.status_code == 201
        global_id = global_resp.json()["id"]

        assigned_resp = await auth_client.post(
            BASE_URL, json=mcp_payload(name=f"assigned-{uuid4().hex[:8]}", scope="project")
        )
        assert assigned_resp.status_code == 201
        assigned_id = assigned_resp.json()["id"]

        assign_resp = await auth_client.post(f"{BASE_URL}/{assigned_id}/projects/{project.id}")
        assert assign_resp.status_code == 201

        unassigned_resp = await auth_client.post(
            BASE_URL, json=mcp_payload(name=f"other-{uuid4().hex[:8]}", scope="project")
        )
        assert unassigned_resp.status_code == 201
        unassigned_id = unassigned_resp.json()["id"]

        response = await auth_client.get(BASE_URL, params={"project_id": str(project.id)})
        assert response.status_code == 200
        returned_ids = {r["id"] for r in response.json()["resources"]}

        assert global_id in returned_ids
        assert assigned_id in returned_ids
        assert unassigned_id not in returned_ids

    async def test_project_id_omitted_returns_all(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Omitting project_id returns all visible integrations (existing behavior)."""
        admin = await user_factory(username=f"pf-all-{uuid4().hex[:6]}", email=f"pf-all-{uuid4().hex[:6]}@t.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        global_resp = await auth_client.post(BASE_URL, json=mcp_payload(name=f"g-{uuid4().hex[:8]}"))
        assert global_resp.status_code == 201
        global_id = global_resp.json()["id"]

        project_resp = await auth_client.post(BASE_URL, json=mcp_payload(name=f"p-{uuid4().hex[:8]}", scope="project"))
        assert project_resp.status_code == 201
        project_id = project_resp.json()["id"]

        response = await auth_client.get(BASE_URL)
        assert response.status_code == 200
        returned_ids = {r["id"] for r in response.json()["resources"]}

        assert global_id in returned_ids
        assert project_id in returned_ids

    async def test_project_id_global_always_included(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Global integrations are always included regardless of project_id value."""
        admin = await user_factory(username=f"pf-ga-{uuid4().hex[:6]}", email=f"pf-ga-{uuid4().hex[:6]}@t.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        global_resp = await auth_client.post(BASE_URL, json=mcp_payload(name=f"ga-{uuid4().hex[:8]}"))
        assert global_resp.status_code == 201
        global_id = global_resp.json()["id"]

        nonexistent_project_id = str(uuid4())
        response = await auth_client.get(BASE_URL, params={"project_id": nonexistent_project_id})
        assert response.status_code == 200
        returned_ids = {r["id"] for r in response.json()["resources"]}

        assert global_id in returned_ids

    async def test_project_user_filtering_by_inaccessible_project(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """A project-user filtering by a project they lack access to sees only globals."""
        admin = await user_factory(username=f"pf-pu-adm-{uuid4().hex[:6]}", email=f"pf-pu-adm-{uuid4().hex[:6]}@t.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        project_a = await _create_project(test_db_session, name=f"pf-a-{uuid4().hex[:8]}")
        project_b = await _create_project(test_db_session, name=f"pf-b-{uuid4().hex[:8]}")

        global_resp = await auth_client.post(BASE_URL, json=mcp_payload(name=f"pu-g-{uuid4().hex[:8]}"))
        assert global_resp.status_code == 201
        global_id = global_resp.json()["id"]

        assigned_resp = await auth_client.post(
            BASE_URL, json=mcp_payload(name=f"pu-b-{uuid4().hex[:8]}", scope="project")
        )
        assert assigned_resp.status_code == 201
        assigned_id = assigned_resp.json()["id"]
        assign_resp = await auth_client.post(f"{BASE_URL}/{assigned_id}/projects/{project_b.id}")
        assert assign_resp.status_code == 201

        proj_user = await user_factory(username=f"pf-pu-{uuid4().hex[:6]}", email=f"pf-pu-{uuid4().hex[:6]}@t.com")
        await make_project_user(test_db_session, proj_user, project_a)
        auth_as(proj_user)

        response = await auth_client.get(BASE_URL, params={"project_id": str(project_b.id)})
        assert response.status_code == 200
        returned_ids = {r["id"] for r in response.json()["resources"]}

        assert global_id in returned_ids
        assert assigned_id not in returned_ids
