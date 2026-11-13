"""Filter testing permissions through real PostgreSQL role resolution and Rego."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.engine import clear_authz_cache
from syntara.authz.evaluator import RegoEvaluator
from syntara.authz.models import Project, RoleAssignment
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
    ("role", "project_scoped", "expected_status"),
    [
        ("admin", False, 200),
        ("project-admin", True, 200),
        ("project-user", True, 200),
        ("auditor", False, 403),
        ("project-auditor", True, 403),
        ("user", False, 403),
        (None, False, 403),
    ],
)
async def test_filter_test_requires_workflow_creation_permission(
    test_db_session: AsyncSession,
    test_user: User,
    role: str | None,
    *,
    project_scoped: bool,
    expected_status: int,
) -> None:
    project = Project(name=f"filter-permissions-{uuid4().hex[:8]}")
    test_db_session.add(project)
    await test_db_session.flush()
    assignment = None
    if role is not None:
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
