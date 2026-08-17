"""Integration tests for the project_eligible policy filter.

Validates that the ``project_eligible=true`` query parameter on
``GET /api/v1/policies`` correctly returns only project-scoped policies
and does not cause a 422 validation error.

Regression test for: https://github.com/syntara-orchestration/syntara/pull/902
"""

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models.policy import Policy


@pytest.fixture
async def _create_test_policies(test_db_session: AsyncSession) -> None:
    """Seed a project-scoped and a system-scoped custom policy."""
    test_db_session.add(
        Policy(
            name="test-project-policy",
            description="Project-scoped policy",
            statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "project"}],
            is_builtin=False,
            scope="project",
            labels={},
        )
    )
    test_db_session.add(
        Policy(
            name="test-system-policy",
            description="System-scoped policy",
            statements=[{"effect": "allow", "actions": ["user:read"], "scope": "any"}],
            is_builtin=False,
            scope="any",
            labels={},
        )
    )
    await test_db_session.commit()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_create_test_policies")
async def test_project_eligible_returns_200(
    admin_client: AsyncClient,
) -> None:
    """GET /policies?project_eligible=true must not return 422."""
    resp = await admin_client.get("/api/v1/policies", params={"project_eligible": "true"})
    assert resp.status_code == 200


@pytest.mark.asyncio
@pytest.mark.usefixtures("_create_test_policies")
async def test_project_eligible_filters_to_project_scope(
    admin_client: AsyncClient,
) -> None:
    """project_eligible=true should only return policies with scope=project or own."""
    resp = await admin_client.get("/api/v1/policies", params={"project_eligible": "true", "limit": 100})
    assert resp.status_code == 200
    data = resp.json()
    for policy in data["resources"]:
        assert policy["scope"] in ("project", "own"), (
            f"Policy '{policy['name']}' has scope '{policy['scope']}', expected 'project' or 'own'"
        )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_create_test_policies")
async def test_project_eligible_with_name_filter(
    admin_client: AsyncClient,
) -> None:
    """project_eligible=true combined with name search must return 200."""
    resp = await admin_client.get(
        "/api/v1/policies",
        params={"project_eligible": "true", "name[contains]": "workflow"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for policy in data["resources"]:
        assert "workflow" in policy["name"].lower()
        assert policy["scope"] in ("project", "own")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_create_test_policies")
async def test_without_project_eligible_returns_all_scopes(
    admin_client: AsyncClient,
) -> None:
    """Without project_eligible, policies of all scopes are returned."""
    resp = await admin_client.get("/api/v1/policies", params={"limit": 100})
    assert resp.status_code == 200
    data = resp.json()
    scopes = {p["scope"] for p in data["resources"]}
    assert len(scopes) > 1, "Expected policies with multiple scopes when project_eligible is not set"
