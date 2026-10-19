"""Inspect and preflight through HTTP, PostgreSQL, Rego and encrypted secrets.

Only Kafka network I/O is replaced. Publication, queries, cursor pagination,
permission resolution, credential decryption/injection and RFC 9457 handlers
are real. These tests do not require a live Kafka broker or Temporal worker.
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
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.router import router
from syntara.eventstreams.services.subscription_service import EventSubscriptionService
from syntara.integrations.models.integration import Integration, IntegrationScope, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
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
    other_workflow: Workflow
    other_project: Project
    integration: Integration
    runtime: Credential
    management: Credential
    subscriptions: dict[str, EventSubscription]

    @property
    def url(self) -> str:
        """Current workflow collection URL."""
        return f"/api/v1/workflows/{self.workflow.id}/event-subscriptions"

    def parameters(self) -> dict[str, str]:
        """Unsaved parameters always identify a runtime credential explicitly."""
        return {
            "transport": "kafka",
            "integration_id": str(self.integration.id),
            "credential_id": str(self.runtime.id),
            "topic": "unsaved.alerts",
        }


async def _publish(
    session: AsyncSession,
    user: User,
    workflow: Workflow,
    integration: Integration,
    credential: Credential,
    topics: dict[str, str],
    version_number: int,
) -> dict[str, EventSubscription]:
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=version_number,
        schema_version="2.0.0",
        created_by=user.id,
        workflow_definition={
            "schema_version": "2.0.0",
            "name": workflow.name,
            "nodes": [],
            "edges": [],
            "triggers": [
                {
                    "id": node,
                    "type": "event_subscribe_trigger",
                    "parameters": {
                        "transport": "kafka",
                        "integration_id": str(integration.id),
                        "credential_id": str(credential.id),
                        "topic": topic,
                    },
                }
                for node, topic in topics.items()
            ],
        },
    )
    session.add(version)
    await session.flush()
    await EventSubscriptionService(session, user).sync_from_published_definition(workflow, version, enabled=True)
    workflow.published_version_id = version.id
    workflow.is_enabled = True
    await session.flush()
    rows = await session.exec(select(EventSubscription).where(EventSubscription.workflow_id == workflow.id))
    return {row.trigger_node_id: row for row in rows.all()}


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
    credential_type = CredentialType(
        name="Kafka-connection",
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
    other_workflow = Workflow(name="another", project_id=test_project_id, created_by=test_user.id)
    session.add_all([integration, workflow, other_workflow])
    await session.flush()
    await _publish(
        session,
        test_user,
        workflow,
        integration,
        runtime,
        {"a": "alerts.a", "b": "alerts.b", "c": "alerts.old", "retired": "alerts.retired"},
        1,
    )
    subscriptions = await _publish(
        session, test_user, workflow, integration, runtime, {"a": "alerts.a", "b": "alerts.b", "c": "alerts.current"}, 2
    )
    await _publish(session, test_user, other_workflow, integration, runtime, {"other": "other.alerts"}, 1)
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
                other_workflow,
                other_project,
                integration,
                runtime,
                management,
                subscriptions,
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


async def test_current_collection_paginates_and_counts_without_retired_or_other_workflows(
    scenario: InspectionScenario,
) -> None:
    first = await scenario.client.get(scenario.url, params={"limit": 2, "include_total": "true", "transport": "kafka"})
    assert first.status_code == 200, first.text
    page = first.json()
    assert page["total"] == 3
    assert len(page["resources"]) == 2
    assert page["next"] is not None
    second = await scenario.client.get(
        scenario.url, params={"limit": 2, "include_total": "true", "cursor": page["next"]}
    )
    assert second.status_code == 200, second.text
    following = second.json()
    assert following["total"] == 3
    assert following["next"] is None
    resources = page["resources"] + following["resources"]
    assert {row["trigger_node_id"] for row in resources} == {"a", "b", "c"}
    assert len({row["id"] for row in resources}) == 3
    assert all(row["workflow_id"] == str(scenario.workflow.id) for row in resources)
    assert all(row["project_id"] == str(scenario.workflow.project_id) for row in resources)
    current = next(row for row in resources if row["trigger_node_id"] == "c")
    assert current["source"]["generation"] == 2
    assert current["source"]["configuration"]["topic"] == "alerts.current"
    previous = await scenario.client.get(scenario.url, params={"limit": 2, "cursor": following["prev"]})
    assert previous.status_code == 200, previous.text
    assert [row["id"] for row in previous.json()["resources"]] == [row["id"] for row in page["resources"]]


async def test_detail_returns_current_source_only_and_safe_missing_errors(scenario: InspectionScenario) -> None:
    response = await scenario.client.get(f"{scenario.url}/{scenario.subscriptions['c'].id}")
    assert response.status_code == 200, response.text
    assert response.json()["source"]["generation"] == 2
    assert response.json()["source"]["configuration"]["topic"] == "alerts.current"
    other = await scenario.session.exec(
        select(EventSubscription).where(EventSubscription.workflow_id == scenario.other_workflow.id)
    )
    for subscription_id in [uuid4(), scenario.subscriptions["retired"].id, other.one().id]:
        missing = await scenario.client.get(f"{scenario.url}/{subscription_id}")
        assert missing.status_code == 404, missing.text
        assert missing.headers["content-type"] == "application/problem+json"
        assert missing.json()["detail"] == "Event subscription not found"


async def test_caller_filters_cannot_expand_workflow_project_or_retired_scope(scenario: InspectionScenario) -> None:
    response = await scenario.client.get(
        scenario.url,
        params={
            "workflow_id[in]": str(scenario.other_workflow.id),
            "project_id": str(scenario.other_project.id),
            "retired": "true",
            "include_total": "true",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 3
    assert {row["trigger_node_id"] for row in response.json()["resources"]} == {"a", "b", "c"}


async def test_mismatched_subscription_project_is_excluded(scenario: InspectionScenario) -> None:
    subscription = scenario.subscriptions["a"]
    subscription.project_id = scenario.other_project.id
    await scenario.session.commit()
    response = await scenario.client.get(scenario.url, params={"include_total": "true"})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    assert str(subscription.id) not in {row["id"] for row in response.json()["resources"]}
    assert (await scenario.client.get(f"{scenario.url}/{subscription.id}")).status_code == 404


async def test_workflow_project_permissions_are_enforced(scenario: InspectionScenario) -> None:
    workflow = Workflow(name="foreign", project_id=scenario.other_project.id, created_by=scenario.user.id)
    scenario.session.add(workflow)
    await scenario.session.commit()
    response = await scenario.client.get(f"/api/v1/workflows/{workflow.id}/event-subscriptions")
    assert response.status_code == 403, response.text
    await _remove_permission(scenario, "workflow:read")
    assert (await scenario.client.get(scenario.url)).status_code == 403
    assert (await scenario.client.get(f"{scenario.url}/{scenario.subscriptions['a'].id}")).status_code == 403


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


@pytest.mark.parametrize(
    "invalid",
    [
        "cross_project_credential",
        "missing_credential",
        "disabled_credential",
        "missing_integration",
        "disabled_integration",
        "unassigned_integration",
    ],
)
async def test_preflight_rejects_unavailable_or_out_of_scope_references(
    scenario: InspectionScenario, invalid: str
) -> None:
    parameters = scenario.parameters()
    if invalid == "cross_project_credential":
        scenario.runtime.project_id = scenario.other_project.id
    elif invalid == "missing_credential":
        parameters["credential_id"] = str(uuid4())
    elif invalid == "disabled_credential":
        scenario.runtime.enabled = False
    elif invalid == "missing_integration":
        parameters["integration_id"] = str(uuid4())
    elif invalid == "disabled_integration":
        scenario.integration.enabled = False
    else:
        scenario.integration.scope = IntegrationScope.PROJECT
    await scenario.session.commit()
    with patch(f"{_KAFKA_MODULE}.create_conn") as connect:
        response = await scenario.client.post(f"{scenario.url}/test", json=parameters)
    assert response.status_code == 422, response.text
    assert response.headers["content-type"] == "application/problem+json"
    connect.assert_not_called()


@pytest.mark.parametrize("field", ["selected_account_id", "execution_service_account_id", "group_id", "source"])
async def test_preflight_rejects_extra_fields_before_network_access(scenario: InspectionScenario, field: str) -> None:
    with patch(f"{_KAFKA_MODULE}.create_conn") as connect:
        response = await scenario.client.post(
            f"{scenario.url}/test", json={**scenario.parameters(), field: str(uuid4())}
        )
    assert response.status_code == 422, response.text
    connect.assert_not_called()


async def test_preflight_failure_remains_sanitized_and_unverified(scenario: InspectionScenario) -> None:
    connection = _connection()
    connection.send.side_effect = TimeoutError(_RUNTIME_PASSWORD)
    with patch(f"{_KAFKA_MODULE}.create_conn", return_value=connection):
        response = await scenario.client.post(f"{scenario.url}/test", json=scenario.parameters())
    assert response.status_code == 200, response.text
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "timeout"
    assert response.json()["topic_read"] == response.json()["group_access"] == "unverified"
    assert _RUNTIME_PASSWORD not in response.text
    connection.close.assert_awaited_once()
