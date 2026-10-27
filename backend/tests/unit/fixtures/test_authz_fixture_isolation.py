"""Routers loaded under one authz fixture must use the next test's evaluator."""

import inspect
from typing import TYPE_CHECKING, Annotated, Any, cast
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from syntara.api import main
from syntara.authz import dependencies
from syntara.authz.evaluator import AuthzEvaluator
from tests.integration import conftest as integration_fixtures
from tests.integration.api import conftest as api_fixtures

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.asyncio
@pytest.mark.parametrize("first_scope", ["allow_all", "policy"])
async def test_router_uses_current_evaluator_after_fixture_teardown(
    monkeypatch: pytest.MonkeyPatch, first_scope: str
) -> None:
    app = FastAPI()
    original_evaluator = object()
    app.state.authz_evaluator = original_evaluator
    monkeypatch.setattr(main, "app", app)
    monkeypatch.setattr(api_fixtures, "app", app)
    fixture = (
        integration_fixtures._mock_evaluator_allow_all if first_scope == "allow_all" else api_fixtures._mock_evaluator
    )
    activate_first = cast("Callable[[pytest.MonkeyPatch], None]", inspect.unwrap(fixture))
    activate_current = cast(
        "Callable[[pytest.MonkeyPatch], None]", inspect.unwrap(integration_fixtures._mock_evaluator_allow_all)
    )

    with monkeypatch.context() as first:
        activate_first(first)
        provider = dependencies.get_authz_evaluator
        evaluator = provider(Request({"type": "http", "app": app}))
        first.setattr(evaluator, "evaluate", MagicMock(return_value={"allowed_projects": []}))

        @app.get("/visibility")
        def visibility(current: Annotated[AuthzEvaluator, Depends(provider)]) -> dict[str, Any]:
            return current.evaluate({})

    with monkeypatch.context() as current:
        activate_current(current)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/visibility")
        assert response.status_code == 200
        assert response.json()["allowed_projects"] == ["*"]

    assert app.state.authz_evaluator is original_evaluator
    assert app.dependency_overrides == {}
