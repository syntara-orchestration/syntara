"""Shared CEL endpoint behavior with actual parsing, evaluation and HTTP validation."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from syntara.auth import get_current_user
from syntara.authz import dependencies as authz_dependencies
from syntara.authz.engine import AllowedProjectsResult
from syntara.core.database.session import get_db
from syntara.core.error_handlers import http_exception_handler, validation_error_handler
from syntara.core.exception_registry import register_exceptions
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.filter_input import EventFilterInput
from syntara.eventstreams.core.filtering import PreparedSubscriptionFilter
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder
from syntara.eventstreams.models.filter_configuration import FilterConfiguration
from syntara.filtering import router as router_module
from syntara.filtering.constants import MAX_EXPRESSION_LENGTH
from syntara.filtering.router import router

_URL = "/api/v1/filtering/test"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Retain real authentication and error handlers without external database access."""
    instance = FastAPI()
    instance.include_router(router, prefix="/api/v1")
    register_exceptions(instance)
    instance.dependency_overrides[get_db] = lambda: MagicMock()
    instance.state.authz_evaluator = MagicMock()
    monkeypatch.setattr(
        authz_dependencies,
        "resolve_allowed_projects",
        AsyncMock(return_value=AllowedProjectsResult(all_projects=False, project_ids=[uuid4()])),
    )

    async def validation(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return validation_error_handler(request, exc)

    async def http_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, HTTPException)
        return http_exception_handler(request, exc)

    instance.add_exception_handler(RequestValidationError, validation)
    instance.add_exception_handler(HTTPException, http_error)
    return instance


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Supply an authenticated project workflow creator; keep CEL evaluation real."""
    app.dependency_overrides[get_current_user] = lambda: MagicMock()
    return TestClient(app)


def test_authentication_is_required(app: FastAPI) -> None:
    response = TestClient(app).post(_URL, json={"expression": "true", "input": None})
    assert response.status_code == 401


@pytest.mark.parametrize("scope", ["system", "project", "none"])
@pytest.mark.parametrize("expression", ["true", "input =="])
def test_workflow_designer_permission_is_required(client: TestClient, monkeypatch, scope: str, expression: str) -> None:
    permission = AsyncMock(
        return_value=AllowedProjectsResult(
            all_projects=scope == "system", project_ids=[uuid4()] if scope == "project" else []
        )
    )
    monkeypatch.setattr(authz_dependencies, "resolve_allowed_projects", permission)
    evaluate = Mock(side_effect=AssertionError("Unauthorized callers must not evaluate CEL"))
    if scope == "none":
        monkeypatch.setattr(router_module, "PreparedFilter", evaluate)
    response = client.post(_URL, json={"expression": expression, "input": {}})
    assert response.status_code == (403 if scope == "none" else 200 if expression == "true" else 422)
    permission.assert_awaited_once()
    call = permission.await_args
    assert call is not None
    assert call.kwargs["resource_type"] == "workflow"
    assert call.kwargs["action"] == "create"
    if scope == "none":
        evaluate.assert_not_called()


@pytest.mark.parametrize(
    ("expression", "value", "outcome", "error_code"),
    [
        ("input == null", None, "match", None),
        ("input == 'critical'", "critical", "match", None),
        ("input == true", True, "match", None),
        ("input > 1", 2, "match", None),
        ("input.all(item, item > 0)", [1, 2], "match", None),
        ("input.ok", {"ok": False}, "no_match", None),
        ("input.missing.nested", {}, "no_match", None),
        ("input", 1, "evaluation_error", "filter_non_boolean"),
        ("input + 1 == 2", "text", "evaluation_error", "filter_wrong_type"),
        (
            "input.text.matches(input.pattern)",
            {"text": "x", "pattern": "["},
            "evaluation_error",
            "filter_evaluation_failed",
        ),
    ],
)
def test_shared_evaluation_outcomes(client: TestClient, expression, value, outcome, error_code) -> None:
    response = client.post(_URL, json={"expression": expression, "input": value})
    assert response.status_code == 200, response.text
    assert response.json() == {"outcome": outcome, "error_code": error_code}


@pytest.mark.parametrize(
    "expression", ["input ==", "other.value", "unknown(input)", 'has(input["field"])', "true && 1", "42", "'text'"]
)
def test_invalid_cel_returns_safe_validation_error(client: TestClient, expression: str) -> None:
    response = client.post(_URL, json={"expression": expression, "input": {}})
    assert response.status_code == 422
    assert response.json()["code"].startswith("filter_")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expression": "true"},
        {"expression": 1, "input": {}},
        {"expression": "true", "input": {}, "workflow_id": "unneeded"},
    ],
)
def test_invalid_requests_are_rejected(client: TestClient, body: object) -> None:
    assert client.post(_URL, json=body).status_code == 422


@pytest.mark.parametrize("expression", [None, "", "  "])
def test_blank_or_omitted_filter_matches(client: TestClient, expression: str | None) -> None:
    body = {"input": {}} if expression is None else {"expression": expression, "input": {}}
    response = client.post(_URL, json=body)
    assert response.status_code == 200
    assert response.json() == {"outcome": "match", "error_code": None}


def test_filtering_specific_sample_limit_is_not_applied(client: TestClient) -> None:
    response = client.post(_URL, json={"expression": "input.size() > 65536", "input": "x" * 65537})
    assert response.status_code == 200
    assert response.json()["outcome"] == "match"


def test_syntax_error_returns_safe_source_location(client: TestClient) -> None:
    response = client.post(_URL, json={"expression": "input.value >", "input": {}})
    assert response.status_code == 422
    detail = response.json()
    assert detail["code"].startswith("filter_")
    assert detail["line"] == 1
    assert detail["column"] > 0


@pytest.mark.parametrize("failure", ["request", "syntax", "evaluation", "json"])
def test_private_samples_and_expressions_are_not_in_diagnostics(client: TestClient, caplog, failure: str) -> None:
    sample_text = "private-cel-preview-content"
    if failure == "json":
        response = client.post(_URL, content='{"' + sample_text + '":', headers={"Content-Type": "application/json"})
    else:
        body = {"expression": f"input.{sample_text}", "input": {"text": sample_text}}
        if failure == "request":
            body[sample_text] = sample_text
        elif failure == "syntax":
            body["expression"] = f"unknown('{sample_text}')"
        else:
            body["expression"] = "input.text + 1 == 2"
        response = client.post(_URL, json=body)
    assert response.status_code == (200 if failure == "evaluation" else 422)
    assert sample_text not in response.text
    assert sample_text not in caplog.text


def test_listener_sample_has_the_same_result_as_listener_filtering(client: TestClient) -> None:
    expression = "input.payload.value.severity == 'critical' && input.headers.env[1].text == 'prod'"
    configuration = FilterConfiguration(expression=expression)
    event = RawEvent(
        value=b'{"severity":"critical"}',
        headers=(RawEventHeader(name="env", value=b"\xff"), RawEventHeader(name="env", value=b"prod")),
        source_metadata=KafkaSourceMetadata(
            integration_id=uuid4(),
            subscription_id=uuid4(),
            source_generation=1,
            received_at=datetime.now(UTC),
            topic="alerts",
            partition=0,
            offset="42",
        ),
    )
    decoded = JsonEventDecoder().decode(event)
    assert isinstance(decoded, EventDecodeSuccess)
    view = EventFilterInput.from_event(event, decoded)
    expected = PreparedSubscriptionFilter(configuration).evaluate(view)
    response = client.post(
        _URL, json={"expression": expression, "input": view.model_dump(mode="json", exclude_unset=True)}
    )
    assert response.status_code == 200, response.text
    assert response.json() == expected.model_dump(mode="json")


def test_infrastructure_failure_is_not_reported_as_an_invalid_expression(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(router_module, "PreparedFilter", Mock(side_effect=OSError("Engine unavailable")))
    response = TestClient(client.app, raise_server_exceptions=False).post(
        _URL, json={"expression": "input.ok", "input": {"ok": True}}
    )
    assert response.status_code == 500
    assert "filter_invalid" not in response.text


def test_oversized_expression_is_rejected_without_compiling_or_echoing_it(client: TestClient, monkeypatch) -> None:
    compile_filter = Mock(side_effect=AssertionError("Oversized source must not be compiled"))
    monkeypatch.setattr(router_module, "PreparedFilter", compile_filter)
    expression = "private-source-" + "x" * MAX_EXPRESSION_LENGTH
    response = client.post(_URL, json={"expression": expression, "input": {}})
    assert response.status_code == 422
    assert "private-source-" not in response.text
    compile_filter.assert_not_called()
