"""Filter testing permissions through real PostgreSQL role resolution and Rego."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.engine import clear_authz_cache
from syntara.authz.evaluator import RegoEvaluator
from syntara.authz.models import Project, Role, RoleAssignment
from syntara.core.database.session import get_db
from syntara.core.exception_registry import register_exceptions
from syntara.core.models import User
from syntara.filtering.router import router

pytestmark = pytest.mark.integration
_URL = "/api/v1/filtering/test"


@pytest.fixture(autouse=True)
def _mock_evaluator_allow_all() -> None:
    """Override the parent mock so this module uses the actual policy evaluator."""


@pytest.mark.parametrize(
    ("role", "project_scoped", "only_action", "expected_status"),
    [
        ("admin", False, None, 200),
        ("project-admin", True, None, 200),
        ("project-user", True, None, 200),
        ("auditor", False, None, 403),
        ("project-auditor", True, None, 403),
        ("user", False, None, 403),
        (None, False, None, 403),
        ("global-create-only", False, "create", 200),
        ("project-create-only", True, "create", 200),
        ("global-update-only", False, "update", 403),
        ("project-update-only", True, "update", 403),
    ],
)
async def test_filter_test_requires_workflow_creation_permission(
    test_db_session: AsyncSession,
    test_user: User,
    role: str | None,
    only_action: str | None,
    *,
    project_scoped: bool,
    expected_status: int,
) -> None:
    project = Project(name=f"filter-permissions-{uuid4().hex[:8]}")
    test_db_session.add(project)
    await test_db_session.flush()
    assignment = None
    if role is not None:
        if only_action is not None:
            policy_scope = "project" if project_scoped else "any"
            test_db_session.add(
                Role(
                    name=role,
                    project_id=project.id if project_scoped else None,
                    scope="project" if project_scoped else "system",
                    policy_names=[f"workflow:{only_action}:{policy_scope}"],
                )
            )
            await test_db_session.flush()
        assignment = RoleAssignment(
            principal_id=test_user.id,
            role_name=role,
            project_id=project.id if project_scoped else None,
        )
        test_db_session.add(assignment)
    await test_db_session.commit()
    clear_authz_cache()
    evaluator = RegoEvaluator()
    evaluator.start()
    app = FastAPI()
    app.state.authz_evaluator = evaluator
    app.include_router(router, prefix="/api/v1")
    register_exceptions(app)

    async def db_override() -> AsyncSession:
        return test_db_session

    async def user_override() -> User:
        return test_user

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = user_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            body = {"expression": "input.severity == 'critical'", "input": {"severity": "critical"}}
            response = await client.post(_URL, json=body)
            assert response.status_code == expected_status, response.text
            if expected_status == 200:
                assert response.json() == {"outcome": "match", "error_code": None}
            else:
                assert response.json()["code"] == "AUTHORIZATION_DENIED"

            if role == "project-user":
                assert assignment is not None
                await test_db_session.delete(assignment)
                await test_db_session.commit()
                clear_authz_cache()
                assert (await client.post(_URL, json=body)).status_code == 403
    finally:
        clear_authz_cache()
        await evaluator.stop()
