"""V1 clients remain usable while v2 lists Kafka alongside existing types."""

import importlib.util
import sys
from collections.abc import AsyncGenerator
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import AllowedProjectsResult
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.integrations import router as current
from syntara.integrations.legacy_router import router as legacy_router
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration, MCPServerConfigurationInput


@pytest_asyncio.fixture
async def auth_client(test_db_session: AsyncSession, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Exercise the real routers and service without unrelated background workers."""
    app = FastAPI()
    app.include_router(legacy_router, prefix="/api/v1")
    app.include_router(current.router, prefix="/api/v2")
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[current.integration_read_visibility] = lambda: AllowedProjectsResult(
        all_projects=True, project_ids=[]
    )
    for route in [*legacy_router.routes, *current.router.routes]:
        for dep in getattr(route, "dependencies", []):
            if isinstance(dep.dependency, (PermissionChecker, VisibilityFilter)):
                app.dependency_overrides[dep.dependency] = lambda: None
    from syntara.core.exception_registry import register_exceptions

    register_exceptions(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _load_old_model(filename: str) -> ModuleType:
    name = f"syntara_api_client.models.legacy_{filename}"
    source = Path(__file__).with_name("fixtures") / f"v1_{filename}.py.txt"
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(source)))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_old_client_parses_v1_pages_while_v2_includes_kafka(
    auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
) -> None:
    legacy = [
        Integration(
            name=name,
            created_by=test_user.id,
            updated_by=test_user.id,
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfigurationInput(base_url="https://example.com"),
        )
        for name in ["A legacy", "C legacy"]
    ]
    kafka = Integration(
        name="B Kafka",
        created_by=test_user.id,
        updated_by=test_user.id,
        integration_type=IntegrationType.KAFKA,
        configuration=KafkaConfiguration(bootstrap_servers=["broker.example.com:9093"], security_protocol="SSL"),
    )
    test_db_session.add_all([*legacy, kafka])
    await test_db_session.commit()
    old_parser = _load_old_model("integration_read")
    vars(old_parser)["IntegrationType"] = vars(_load_old_model("integration_type"))["IntegrationType"]

    first = await auth_client.get("/api/v1/integrations", params={"limit": 1, "sort": "name", "include_total": "true"})
    assert first.status_code == 200
    page = first.json()
    assert page["total"] == 2
    assert old_parser.IntegrationRead.from_dict(page["resources"][0]).name == "A legacy"
    assert page["next"]
    second = await auth_client.get(
        "/api/v1/integrations", params={"limit": 1, "sort": "name", "cursor": page["next"], "include_total": "true"}
    )
    assert second.status_code == 200
    assert second.json()["total"] == 2
    assert old_parser.IntegrationRead.from_dict(second.json()["resources"][0]).name == "C legacy"
    assert second.json()["next"] is None

    invalid_type = await auth_client.get("/api/v1/integrations", params={"integration_type": "kafka"})
    assert invalid_type.status_code == 422

    excluded = await auth_client.get(
        "/api/v1/integrations", params={"integration_type[in]": "kafka", "include_total": "true"}
    )
    assert excluded.status_code == 200
    assert excluded.json()["resources"] == []
    assert excluded.json()["total"] == 0

    combined = await auth_client.get("/api/v2/integrations", params={"sort": "name", "include_total": "true"})
    assert combined.status_code == 200
    assert combined.json()["total"] == 3
    rows = combined.json()["resources"]
    assert [row["integration_type"] for row in rows] == ["mcp_server", "kafka", "mcp_server"]
    assert rows[1]["configuration"]["security_protocol"] == "SSL"
    assert "kafka_configuration" not in rows[1]
    assert (await auth_client.get(f"/api/v1/integrations/{kafka.id}")).status_code == 404
    assert (await auth_client.get(f"/api/v2/integrations/{kafka.id}")).status_code == 200


@pytest.mark.asyncio
async def test_v1_rejects_kafka_create_and_discovery(auth_client: AsyncClient) -> None:
    configuration = {
        "integration_type": "kafka",
        "bootstrap_servers": ["broker.example.com:9093"],
        "security_protocol": "SSL",
    }
    payload = {"integration_type": "kafka", "configuration": configuration}
    assert (await auth_client.post("/api/v1/integrations", json={**payload, "name": "Kafka"})).status_code == 422
    assert (await auth_client.post("/api/v1/integrations/discover", json=payload)).status_code == 422


@pytest.mark.parametrize("base_path", ["", "/api/v1", "/deployment/api/v1", "/deployment/api/v2"])
def test_generated_v2_client_selects_v2_and_preserves_deployment_prefix(base_path: str) -> None:
    """Path-level version selection must not append v2 beneath a v1 base URL."""
    import httpx
    from syntara_api_client.api.integrations import v2_list_integrations
    from syntara_api_client.client import AuthenticatedClient

    prefix = base_path.split("/api/")[0]
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"resources": [], "next": None, "prev": None, "total": 0})

    with httpx.Client(base_url=f"https://example.com{base_path}", transport=httpx.MockTransport(respond)) as transport:
        client = AuthenticatedClient(base_url=f"https://example.com{base_path}", token=str(uuid4())).set_httpx_client(
            transport
        )
        response = v2_list_integrations.sync_detailed(client=client)
    assert response.status_code == 200
    assert requests[0].url.path == f"{prefix}/api/v2/integrations"


@pytest.mark.asyncio
async def test_generated_async_v2_client_selects_v2() -> None:
    """The async Python client follows the same versioned URL rule."""
    import httpx
    from syntara_api_client.api.integrations import v2_list_integrations
    from syntara_api_client.client import AuthenticatedClient

    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"resources": [], "next": None, "prev": None, "total": 0})

    async with httpx.AsyncClient(
        base_url="https://example.com/deployment/api/v1", transport=httpx.MockTransport(respond)
    ) as transport:
        client = AuthenticatedClient(
            base_url="https://example.com/deployment/api/v1", token=str(uuid4())
        ).set_async_httpx_client(transport)
        response = await v2_list_integrations.asyncio_detailed(client=client)
    assert response.status_code == 200
    assert requests[0].url.path == "/deployment/api/v2/integrations"


def test_regenerated_v1_client_preserves_the_original_enum_filter() -> None:
    """SDK callers using IntegrationType must not silently lose their filter."""
    import httpx
    from syntara_api_client.api.integrations import list_integrations
    from syntara_api_client.client import AuthenticatedClient
    from syntara_api_client.models.integration_type import IntegrationType

    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"resources": [], "next": None, "prev": None, "total": 0})

    with httpx.Client(base_url="https://example.com/api/v1", transport=httpx.MockTransport(respond)) as transport:
        client = AuthenticatedClient(base_url="https://example.com/api/v1", token=str(uuid4())).set_httpx_client(
            transport
        )
        response = list_integrations.sync_detailed(client=client, integration_type=IntegrationType.MCP_SERVER)
    assert response.status_code == 200
    assert requests[0].url.path == "/api/v1/integrations"
    assert requests[0].url.params["integration_type"] == "mcp_server"
    assert set(IntegrationType) == {
        IntegrationType.MCP_SERVER,
        IntegrationType.LLM_PROVIDER,
        IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
    }


@pytest.mark.asyncio
async def test_v1_writes_keep_configuration_and_partial_update_semantics(auth_client: AsyncClient) -> None:
    """Legacy clients can still create and edit their original integration types."""
    from unittest.mock import patch

    payload = {
        "name": "Legacy MCP write",
        "integration_type": "mcp_server",
        "configuration": {"integration_type": "mcp_server", "base_url": "https://example.com"},
    }
    with patch("syntara.integrations.services.integration_service.validate_integration_configuration_no_ssrf"):
        created = await auth_client.post("/api/v1/integrations", json=payload)
    assert created.status_code == 201
    original = created.json()
    parser = _load_old_model("integration_read")
    assert parser.IntegrationRead.from_dict(original).configuration.base_url == "https://example.com"
    updated = await auth_client.patch(f"/api/v1/integrations/{original['id']}", json={"description": "Updated by v1"})
    assert updated.status_code == 200
    assert updated.json()["name"] == original["name"]
    assert updated.json()["configuration"] == original["configuration"]
    assert updated.json()["description"] == "Updated by v1"

    mismatched = await auth_client.post(
        "/api/v1/integrations",
        json={**payload, "configuration": {"integration_type": "llm_provider", "provider_hint": "openai"}},
    )
    assert mismatched.status_code == 422
