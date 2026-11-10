"""Preflight through HTTP, PostgreSQL, Rego and encrypted secrets.

Only Kafka network I/O is replaced. Permission resolution, credential
resolution and RFC 9457 handlers are real; no live Kafka or Temporal is needed.
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.engine import AuthzRequest, authorize, clear_authz_cache
from syntara.authz.evaluator import RegoEvaluator
from syntara.authz.models import Policy, Project, Role, RoleAssignment
from syntara.core.database.session import get_db
from syntara.core.error_handlers import validation_error_handler
from syntara.core.exception_registry import register_exceptions
from syntara.core.lib.encryption import SecretEncryptor
from syntara.core.models import User
from syntara.core.services.secret_service import SecretService
from syntara.core.services.storage_backend import DatabaseBackend
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.router import router
from syntara.integrations.models.integration import Integration, IntegrationScope, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.models.workflow import Workflow
from tests.fixtures.encryption import OLD_KEY

pytestmark = pytest.mark.integration
_ACTIONS = ["workflow:read", "workflow:update", "integration:read", "credential:use"]
_RUNTIME_PASSWORD = "runtime-test-password"  # noqa: S105
_MANAGEMENT_PASSWORD = "management-test-password"  # noqa: S105
_KAFKA_MODULE = "syntara.eventstreams.adapters.kafka_preflight"


@pytest.fixture(autouse=True)
def _mock_evaluator_allow_all() -> None:
    """Override the parent's allow-all mock: these tests use actual Rego."""


@dataclass
class InspectionScenario:
    """Persisted resources and an authenticated in-process HTTP client."""

    session: AsyncSession
    client: AsyncClient
    user: User
    evaluator: RegoEvaluator
    policy: Policy
    workflow: Workflow
    other_project: Project
    integration: Integration
    runtime: Credential

    @property
    def url(self) -> str:
        """Current workflow collection URL."""
        return f"/api/v1/workflows/{self.workflow.id}/event_subscriptions"

    def parameters(self) -> dict[str, str]:
        """Unsaved parameters always identify a runtime credential explicitly."""
        return {
            "integration_id": str(self.integration.id),
            "credential_id": str(self.runtime.id),
            "topic": "unsaved.alerts",
        }


@pytest_asyncio.fixture
async def scenario(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[InspectionScenario, None]:
    """Use genuine permissions and secrets without the application's external services."""
    session = test_db_session
    other_project = Project(name=f"other-{uuid4().hex[:8]}")
    session.add(other_project)
    await session.flush()
    policy = Policy(
        name=f"designer-{uuid4().hex[:8]}",
        statements=[
            {"effect": "allow", "actions": _ACTIONS, "scope": "any"},
        ],
    )
    role = Role(name=f"designer-{uuid4().hex[:8]}", policy_names=[policy.name])
    session.add_all([policy, role])
    session.add(RoleAssignment(principal_id=test_user.id, role_name=role.name, project_id=test_project_id))
    existing_type = await session.exec(select(CredentialType).where(CredentialType.name == "Kafka"))
    credential_type = existing_type.first()
    if credential_type is None:
        credential_type = CredentialType(
            name="Kafka",
            inputs={},
            managed=True,
            injectors={
                "extra_vars": {"kafka_username": "{{username}}", "kafka_password": "{{password}}"},
            },
        )
        session.add(credential_type)
        await session.flush()
    secrets = SecretService(session, SecretEncryptor(OLD_KEY), DatabaseBackend(session))
    credentials = []
    for name, password in [("runtime", _RUNTIME_PASSWORD), ("management", _MANAGEMENT_PASSWORD)]:
        secret_id = await secrets.create_secret({"username": name, "password": password})
        credential = Credential(
            name=name,
            credential_type_id=credential_type.id,
            project_id=test_project_id,
            created_by=test_user.id,
            secret_id=secret_id,
            enabled=True,
        )
        session.add(credential)
        credentials.append(credential)
    runtime, management = credentials
    await session.flush()
    integration = Integration(
        name="kafka",
        integration_type=IntegrationType.KAFKA,
        created_by=test_user.id,
        configuration=KafkaConfiguration(bootstrap_servers=["broker.example.com:9093"]),
        management_credential_id=management.id,
        enabled=True,
    )
    workflow = Workflow(name="inspected", project_id=test_project_id, created_by=test_user.id)
    session.add_all([integration, workflow])
    await session.commit()
    evaluator = RegoEvaluator()
    evaluator.start()
    app = FastAPI()
    app.state.authz_evaluator = evaluator
    app.include_router(router, prefix="/api/v1")
    register_exceptions(app)

    def request_validation_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return validation_error_handler(request, exc)

    app.add_exception_handler(RequestValidationError, request_validation_error)

    async def db_override() -> AsyncSession:
        return session

    async def user_override() -> User:
        return test_user

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = user_override
    monkeypatch.setattr("syntara.eventstreams.router.create_secret_service", lambda _db: secrets)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield InspectionScenario(
                session,
                client,
                test_user,
                evaluator,
                policy,
                workflow,
                other_project,
                integration,
                runtime,
            )
    finally:
        clear_authz_cache()
        await evaluator.stop()


async def _remove_permission(scenario: InspectionScenario, action: str) -> None:
    scenario.policy.statements = [{"effect": "allow", "scope": "any", "actions": [a for a in _ACTIONS if a != action]}]
    scenario.session.add(scenario.policy)
    await scenario.session.commit()
    clear_authz_cache()


def _connection() -> MagicMock:
    connection = MagicMock(spec=["send", "close"])
    connection.send = AsyncMock(
        return_value=type(
            "Metadata",
            (),
            {
                "topics": [(0, "unsaved.alerts", False, [(0, 0, 1, [1], [1], [])])],
            },
        )()
    )
    connection.close = AsyncMock()
    return connection


async def test_preflight_decrypts_runtime_credential_without_writes_or_execution_permission(
    scenario: InspectionScenario,
) -> None:
    project = await scenario.session.get(Project, scenario.workflow.project_id)
    assert project is not None
    denied = await authorize(
        scenario.session,
        scenario.evaluator,
        AuthzRequest(
            user_id=scenario.user.id,
            resource_type="execution",
            action="run",
            resource_id="",
            resource_project=project.name,
        ),
    )
    assert not denied.allowed
    statements: list[str] = []

    def capture(
        _conn: object, _cursor: object, statement: str, _parameters: object, _context: object, _many: object
    ) -> None:
        statements.append(statement)

    bind = scenario.session.get_bind()
    event.listen(bind, "before_cursor_execute", capture)
    connection = _connection()
    try:
        with patch(f"{_KAFKA_MODULE}.create_conn", return_value=connection) as connect:
            response = await scenario.client.post(f"{scenario.url}/test", json=scenario.parameters())
    finally:
        event.remove(bind, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    assert response.json()["connection"] == response.json()["topic_metadata"] == "verified"
    assert response.json()["topic_read"] == response.json()["group_access"] == "unverified"
    assert connect.call_args.kwargs["sasl_plain_username"] == "runtime"
    assert connect.call_args.kwargs["sasl_plain_password"] == _RUNTIME_PASSWORD
    assert _RUNTIME_PASSWORD not in response.text
    assert _MANAGEMENT_PASSWORD not in response.text
    assert statements
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    request = connection.send.call_args.args[0].prepare({3: (4, 5)})
    assert request.topics == ["unsaved.alerts"]
    assert request.allow_auto_topic_creation is False
    assert [call[0] for call in connection.method_calls] == ["send", "close"]


@pytest.mark.parametrize("action", ["workflow:update", "integration:read", "credential:use"])
async def test_preflight_requires_each_resource_permission(scenario: InspectionScenario, action: str) -> None:
    await _remove_permission(scenario, action)
    with patch(f"{_KAFKA_MODULE}.create_conn") as connect:
        response = await scenario.client.post(f"{scenario.url}/test", json=scenario.parameters())
    assert response.status_code == 403, response.text
    assert response.headers["content-type"] == "application/problem+json"
    connect.assert_not_called()


@pytest.mark.ssrf_enforced
async def test_preflight_rejects_blocked_broker_before_credential_resolution(scenario: InspectionScenario) -> None:
    """Apply the real outbound policy and return a safe RFC 9457 error."""
    scenario.integration.configuration = KafkaConfiguration(bootstrap_servers=["169.254.169.254:9093"])
    await scenario.session.commit()
    with (
        patch("syntara.eventstreams.services.inspection_service.resolve_listener_kafka_login") as resolve,
        patch(f"{_KAFKA_MODULE}.create_conn") as connect,
    ):
        response = await scenario.client.post(f"{scenario.url}/test", json=scenario.parameters())
    assert response.status_code == 422, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == (
        "bootstrap_servers must not resolve to a private, reserved, or cloud metadata address."
    )
    assert "169.254.169.254" not in response.text
    resolve.assert_not_called()
    connect.assert_not_called()


@pytest.mark.parametrize(
    "invalid",
    [
        "cross_project_credential",
        "disabled_credential",
        "missing_integration",
        "unassigned_integration",
    ],
)
async def test_preflight_rejects_unavailable_or_out_of_scope_references(
    scenario: InspectionScenario, invalid: str
) -> None:
    parameters = scenario.parameters()
    if invalid == "cross_project_credential":
        scenario.runtime.project_id = scenario.other_project.id
    elif invalid == "disabled_credential":
        scenario.runtime.enabled = False
    elif invalid == "missing_integration":
        parameters["integration_id"] = str(uuid4())
    else:
        scenario.integration.scope = IntegrationScope.PROJECT
    await scenario.session.commit()
    with patch(f"{_KAFKA_MODULE}.create_conn") as connect:
        response = await scenario.client.post(f"{scenario.url}/test", json=parameters)
    assert response.status_code == 422, response.text
    assert response.headers["content-type"] == "application/problem+json"
    connect.assert_not_called()
