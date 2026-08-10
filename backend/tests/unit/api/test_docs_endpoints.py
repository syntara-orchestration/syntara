"""Tests for OpenAPI documentation endpoint gating.

The production FastAPI app is a module-level singleton whose ``docs_url``
is set at import time and cannot be toggled per-test.  These tests use
standalone ``FastAPI`` instances (via ``_make_app``) to verify the
conditional behavior in isolation: given a particular toggle value, do
the doc endpoints appear or disappear as expected?

The ``TestAPIDocsSettings`` class separately verifies that the
``enable_api_docs`` setting loads correctly from env vars and defaults.
Together the two layers confirm that the wiring in ``main.py`` will
produce the right result when the real setting is read at startup.

Note: The production app now serves custom authenticated doc endpoints
at ``/api/v1/docs``, ``/api/v1/redoc``, and ``/api/v1/openapi.json``
(see ``test_discovery_endpoints.py``).  The standalone ``_make_app``
tests here verify the abstract toggling logic in isolation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from syntara.api.constants import API_V1_PATH_PREFIX, API_V1_VERSION
from syntara.api.main import swagger_ui_parameters
from syntara.core.config.base import get_settings
from syntara.core.router_discovery import iter_api_routes

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager


def _make_app(*, enable_docs: bool, enable_try_it_out: bool = False) -> FastAPI:
    """Create a minimal FastAPI app with doc endpoints toggled."""
    app = FastAPI(
        title="Test API",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
        swagger_ui_parameters=swagger_ui_parameters(enable_try_it_out=enable_try_it_out),
    )

    @app.get("/", tags=["Root"])
    async def root() -> dict[str, str]:
        response: dict[str, str] = {"message": f"{get_settings().product_name} API", "version": API_V1_VERSION}
        if enable_docs:
            response["docs"] = "/docs"
        return response

    return app


# ---------------------------------------------------------------------------
# Docs disabled (production default)
# ---------------------------------------------------------------------------


class TestDocsDisabled:
    """When enable_api_docs=False, doc endpoints must not exist."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(_make_app(enable_docs=False))

    def test_docs_returns_404(self, client: TestClient) -> None:
        response = client.get("/docs")
        assert response.status_code == 404

    def test_redoc_returns_404(self, client: TestClient) -> None:
        response = client.get("/redoc")
        assert response.status_code == 404

    def test_openapi_json_returns_404(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 404

    def test_root_omits_docs_link(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "docs" not in response.json()


# ---------------------------------------------------------------------------
# Docs enabled (development)
# ---------------------------------------------------------------------------


class TestDocsEnabled:
    """When enable_api_docs=True, doc endpoints must be served."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(_make_app(enable_docs=True))

    def test_docs_returns_200(self, client: TestClient) -> None:
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_returns_200(self, client: TestClient) -> None:
        response = client.get("/redoc")
        assert response.status_code == 200

    def test_openapi_json_returns_200(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data

    def test_root_includes_docs_link(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["docs"] == "/docs"


# ---------------------------------------------------------------------------
# Settings integration
# ---------------------------------------------------------------------------


class TestAPIDocsSettings:
    """The enable_api_docs setting defaults to False and is toggleable."""

    def test_default_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from syntara.core.config.base import get_settings

        # Override local .env so this asserts the production default.
        monkeypatch.setenv("APP_ENABLE_API_DOCS", "false")
        get_settings.cache_clear()
        try:
            assert get_settings().enable_api_docs is False
        finally:
            get_settings.cache_clear()

    def test_env_var_enables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from syntara.core.config.base import get_settings

        monkeypatch.setenv("APP_ENABLE_API_DOCS", "true")
        get_settings.cache_clear()
        try:
            assert get_settings().enable_api_docs is True
        finally:
            get_settings.cache_clear()

    def test_override_settings(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        from syntara.core.config.base import get_settings

        with override_settings(enable_api_docs=True):
            assert get_settings().enable_api_docs is True

    def test_field_default_on_class(self) -> None:
        from syntara.core.config.base import APIDocsSettings

        settings = APIDocsSettings()
        assert settings.enable_api_docs is False


class TestTryItOutSettings:
    """The enable_try_it_out setting defaults to False and is toggleable."""

    def test_default_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENABLE_TRY_IT_OUT", "false")
        get_settings.cache_clear()
        try:
            assert get_settings().enable_try_it_out is False
        finally:
            get_settings.cache_clear()

    def test_env_var_enables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENABLE_TRY_IT_OUT", "true")
        get_settings.cache_clear()
        try:
            assert get_settings().enable_try_it_out is True
        finally:
            get_settings.cache_clear()

    def test_override_settings(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        with override_settings(enable_try_it_out=True):
            assert get_settings().enable_try_it_out is True

    def test_field_default_on_class(self) -> None:
        from syntara.core.config.base import APIDocsSettings

        settings = APIDocsSettings()
        assert settings.enable_try_it_out is False


# ---------------------------------------------------------------------------
# Try it out Swagger UI wiring
# ---------------------------------------------------------------------------


class TestSwaggerUiParameters:
    """swagger_ui_parameters() maps the toggle to Swagger UI config correctly."""

    def test_disabled_hides_try_it_out(self) -> None:
        params = swagger_ui_parameters(enable_try_it_out=False)
        assert params["tryItOutEnabled"] is False
        assert params["supportedSubmitMethods"] == []

    def test_enabled_allows_all_methods(self) -> None:
        params = swagger_ui_parameters(enable_try_it_out=True)
        assert params["tryItOutEnabled"] is True
        assert params["supportedSubmitMethods"] == [
            "get",
            "put",
            "post",
            "delete",
            "options",
            "head",
            "patch",
            "trace",
        ]


class TestTryItOutDocsRendering:
    """Swagger UI HTML embeds the correct Try it out configuration."""

    def test_docs_html_disables_try_it_out_by_default(self) -> None:
        client = TestClient(_make_app(enable_docs=True, enable_try_it_out=False))
        response = client.get("/docs")
        assert response.status_code == 200
        assert '"supportedSubmitMethods": []' in response.text
        assert '"tryItOutEnabled": false' in response.text

    def test_docs_html_enables_try_it_out_when_configured(self) -> None:
        client = TestClient(_make_app(enable_docs=True, enable_try_it_out=True))
        response = client.get("/docs")
        assert response.status_code == 200
        assert '"tryItOutEnabled": true' in response.text
        # JSON list of methods is embedded; empty list must not be present.
        assert '"supportedSubmitMethods": []' not in response.text
        assert json.dumps(swagger_ui_parameters(enable_try_it_out=True)["supportedSubmitMethods"]) in response.text


# ---------------------------------------------------------------------------
# Production app wiring
# ---------------------------------------------------------------------------


class TestDocsEnabledWiring:
    """Cover True branches of enable_api_docs conditionals in main.py."""

    def test_version_includes_docs_links_when_enabled(self) -> None:
        import syntara.api.main as main_module
        from syntara.auth.dependencies import get_current_user
        from syntara.core.models.user import User

        async def mock_user() -> User:
            return User(username="testuser", email="test@test.com", first_name="Test")

        original = main_module._settings.enable_api_docs
        object.__setattr__(main_module._settings, "enable_api_docs", True)
        main_module.app.dependency_overrides[get_current_user] = mock_user
        try:
            client = TestClient(main_module.app, raise_server_exceptions=False)
            response = client.get(f"{API_V1_PATH_PREFIX}/version")
            assert response.status_code == 200
            assert response.json()["links"]["docs"] == f"{API_V1_PATH_PREFIX}/docs"
        finally:
            object.__setattr__(main_module._settings, "enable_api_docs", original)
            main_module.app.dependency_overrides.pop(get_current_user, None)

    def test_docs_routes_registered_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        import syntara.api.main as main_module
        from syntara.core.config.base import get_settings

        monkeypatch.setenv("APP_ENABLE_API_DOCS", "true")
        get_settings.cache_clear()
        try:
            importlib.reload(main_module)
            route_paths = [r.path for r in iter_api_routes(main_module.app)]
            assert f"{API_V1_PATH_PREFIX}/docs" in route_paths
            assert f"{API_V1_PATH_PREFIX}/redoc" in route_paths
            assert f"{API_V1_PATH_PREFIX}/openapi.json" in route_paths
        finally:
            # Force production defaults so later tests are not polluted by .env.
            monkeypatch.setenv("APP_ENABLE_API_DOCS", "false")
            monkeypatch.setenv("APP_ENABLE_TRY_IT_OUT", "false")
            get_settings.cache_clear()
            importlib.reload(main_module)

    def test_custom_docs_try_it_out_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        import syntara.api.main as main_module
        from syntara.auth.dependencies import get_current_user
        from syntara.core.models.user import User

        async def mock_user() -> User:
            return User(username="testuser", email="test@test.com", first_name="Test")

        monkeypatch.setenv("APP_ENABLE_API_DOCS", "true")
        monkeypatch.setenv("APP_ENABLE_TRY_IT_OUT", "false")
        get_settings.cache_clear()
        try:
            importlib.reload(main_module)
            main_module.app.dependency_overrides[get_current_user] = mock_user
            client = TestClient(main_module.app, raise_server_exceptions=False)
            response = client.get(f"{API_V1_PATH_PREFIX}/docs")
            assert response.status_code == 200
            assert '"tryItOutEnabled": false' in response.text
            assert '"supportedSubmitMethods": []' in response.text
        finally:
            main_module.app.dependency_overrides.pop(get_current_user, None)
            monkeypatch.setenv("APP_ENABLE_API_DOCS", "false")
            monkeypatch.setenv("APP_ENABLE_TRY_IT_OUT", "false")
            get_settings.cache_clear()
            importlib.reload(main_module)

    def test_custom_docs_try_it_out_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        import syntara.api.main as main_module
        from syntara.auth.dependencies import get_current_user
        from syntara.core.models.user import User

        async def mock_user() -> User:
            return User(username="testuser", email="test@test.com", first_name="Test")

        monkeypatch.setenv("APP_ENABLE_API_DOCS", "true")
        monkeypatch.setenv("APP_ENABLE_TRY_IT_OUT", "true")
        get_settings.cache_clear()
        try:
            importlib.reload(main_module)
            main_module.app.dependency_overrides[get_current_user] = mock_user
            client = TestClient(main_module.app, raise_server_exceptions=False)
            response = client.get(f"{API_V1_PATH_PREFIX}/docs")
            assert response.status_code == 200
            assert '"tryItOutEnabled": true' in response.text
            assert '"supportedSubmitMethods": []' not in response.text
        finally:
            main_module.app.dependency_overrides.pop(get_current_user, None)
            monkeypatch.setenv("APP_ENABLE_API_DOCS", "false")
            monkeypatch.setenv("APP_ENABLE_TRY_IT_OUT", "false")
            get_settings.cache_clear()
            importlib.reload(main_module)


class TestProductionAppWiring:
    """Verify the real app has correct doc endpoint wiring for coverage."""

    def test_builtin_docs_url_disabled(self) -> None:
        from syntara.api.main import app as real_app

        assert real_app.docs_url is None

    def test_builtin_redoc_url_disabled(self) -> None:
        from syntara.api.main import app as real_app

        assert real_app.redoc_url is None

    def test_builtin_openapi_url_disabled(self) -> None:
        from syntara.api.main import app as real_app

        assert real_app.openapi_url is None

    def test_builtin_swagger_ui_params_none(self) -> None:
        from syntara.api.main import app as real_app

        assert real_app.swagger_ui_parameters is None

    def test_version_omits_docs_links_when_disabled(self) -> None:
        from syntara.api.main import app as real_app
        from syntara.auth.dependencies import get_current_user
        from syntara.core.models.user import User

        async def mock_user() -> User:
            return User(username="testuser", email="test@test.com", first_name="Test")

        real_app.dependency_overrides[get_current_user] = mock_user
        try:
            client = TestClient(real_app, raise_server_exceptions=False)
            response = client.get(f"{API_V1_PATH_PREFIX}/version")
            assert response.status_code == 200
            assert response.json()["links"] is None
        finally:
            real_app.dependency_overrides.pop(get_current_user, None)
