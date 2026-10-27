"""Original v1 clients stay compatible with the separate Kafka resource."""

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
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration, MCPServerConfigurationInput


@pytest_asyncio.fixture
async def auth_client(test_db_session: AsyncSession, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Exercise the real routers and service without unrelated background workers."""
    app = FastAPI()
    app.include_router(current.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[current.integration_read_visibility] = lambda: AllowedProjectsResult(
        all_projects=True, project_ids=[]
    )
    for route in current.router.routes:
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
async def test_old_client_parses_pages_while_kafka_is_separate(
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

    combined = await auth_client.get("/api/v1/kafka_integrations", params={"sort": "name", "include_total": "true"})
    assert combined.status_code == 200
    assert combined.json()["total"] == 1
    rows = combined.json()["resources"]
    assert [row["integration_type"] for row in rows] == ["kafka"]
    assert rows[0]["configuration"]["security_protocol"] == "SSL"
    assert "kafka_configuration" not in rows[0]
    assert (await auth_client.get(f"/api/v1/integrations/{kafka.id}")).status_code == 404
    assert (await auth_client.get(f"/api/v1/kafka_integrations/{kafka.id}")).status_code == 200


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


@pytest.mark.asyncio
async def test_kafka_writes_are_isolated_and_preserve_omitted_fields(auth_client: AsyncClient) -> None:
    """Kafka-only writes do not widen the original v1 request contract."""
    from unittest.mock import patch

    configuration = {
        "integration_type": "kafka",
        "bootstrap_servers": ["broker.example.com:9093"],
        "security_protocol": "SSL",
    }
    payload = {
        "name": "Kafka additive API",
        "configuration": {
            "integration_type": "kafka",
            "bootstrap_servers": ["broker.example.com:9093"],
            "security_protocol": "SSL",
        },
    }
    with patch("syntara.integrations.services.integration_service.validate_integration_configuration_no_ssrf"):
        created = await auth_client.post("/api/v1/kafka_integrations", json=payload)
    assert created.status_code == 201
    row = created.json()
    assert row["integration_type"] == "kafka"
    assert row["management_credential_id"] is None
    assert row["configuration"]["security_protocol"] == "SSL"
    updated = await auth_client.patch(f"/api/v1/kafka_integrations/{row['id']}", json={"description": "Edited"})
    assert updated.status_code == 200
    assert updated.json()["configuration"] == row["configuration"]
    assert (
        await auth_client.patch(f"/api/v1/integrations/{row['id']}", json={"description": "Legacy"})
    ).status_code == 404
    assert (
        await auth_client.post("/api/v1/kafka_integrations", json={**payload, "integration_type": "mcp_server"})
    ).status_code == 422
    no_sasl_login = await auth_client.patch(
        f"/api/v1/kafka_integrations/{row['id']}",
        json={"configuration": {**configuration, "security_protocol": "SASL_SSL"}},
    )
    assert no_sasl_login.status_code == 422


@pytest.mark.asyncio
async def test_kafka_resource_cannot_read_or_update_legacy_id(
    auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
) -> None:
    legacy = Integration(
        name="Legacy isolation",
        integration_type=IntegrationType.MCP_SERVER,
        configuration=MCPServerConfigurationInput(base_url="https://example.com"),
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(legacy)
    await test_db_session.commit()
    assert (await auth_client.get(f"/api/v1/kafka_integrations/{legacy.id}")).status_code == 404
    assert (
        await auth_client.patch(f"/api/v1/kafka_integrations/{legacy.id}", json={"enabled": False})
    ).status_code == 404
    excluded = await auth_client.get(
        "/api/v1/kafka_integrations", params={"integration_type[in]": "mcp_server", "include_total": "true"}
    )
    assert excluded.status_code == 200
    assert excluded.json()["resources"] == []
    assert excluded.json()["total"] == 0


@pytest.mark.asyncio
async def test_kafka_filters_and_totals_apply_before_pagination(
    auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
) -> None:
    """Exercise the shared v1 filter contract on the isolated Kafka collection."""
    rows = [
        Integration(
            name=name,
            enabled=enabled,
            integration_type=IntegrationType.KAFKA,
            configuration=KafkaConfiguration(bootstrap_servers=["broker.example.com:9093"], security_protocol="SSL"),
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        for name, enabled in [("A orders", True), ("B orders", True), ("C orders", False), ("Other", True)]
    ]
    rows.append(
        Integration(
            name="A orders legacy",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfigurationInput(base_url="https://example.com"),
            created_by=test_user.id,
            updated_by=test_user.id,
        )
    )
    test_db_session.add_all(rows)
    await test_db_session.commit()
    params = {"limit": "1", "sort": "name", "include_total": "true", "enabled": "true", "name[contains]": "orders"}
    first = await auth_client.get("/api/v1/kafka_integrations", params=params)
    assert first.status_code == 200
    page = first.json()
    assert page["total"] == 2
    assert [item["name"] for item in page["resources"]] == ["A orders"]
    assert page["next"]
    second = await auth_client.get("/api/v1/kafka_integrations", params={**params, "cursor": page["next"]})
    assert second.status_code == 200
    assert second.json()["total"] == 2
    assert [item["name"] for item in second.json()["resources"]] == ["B orders"]
    assert second.json()["next"] is None
