"""Tests for API discovery and version endpoints.

Covers the three-tier discovery hierarchy against the real production app:
- GET /api          — authenticated, lists available API versions
- GET /api/v1       — authenticated, lists v1 endpoints
- GET /api/v1/version — authenticated, returns full version details

Also verifies that unauthenticated doc endpoints at /api_docs/v1/ are
accessible without auth when enabled, and that old root-level doc paths
no longer serve anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import Generator

from syntara.api.constants import API_DOCS_V1_PATH_PREFIX, API_V1_PATH_PREFIX, API_V1_VERSION

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_client() -> Generator[TestClient, None, None]:
    from syntara.api.main import app
    from syntara.auth.dependencies import get_current_user
    from syntara.core.models.user import User

    async def mock_user() -> User:
        return User(username="testuser", email="test@test.com", first_name="Test")

    app.dependency_overrides[get_current_user] = mock_user
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauth_client() -> TestClient:
    from syntara.api.main import app
    from syntara.auth.dependencies import get_current_user

    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /api — authenticated discovery
# ---------------------------------------------------------------------------


class TestApiDiscovery:
    """GET /api requires auth and returns available API versions."""

    def test_returns_200(self, auth_client: TestClient) -> None:
        response = auth_client.get("/api")
        assert response.status_code == 200

    def test_current_version(self, auth_client: TestClient) -> None:
        data = auth_client.get("/api").json()
        assert data["current_version"] == API_V1_PATH_PREFIX

    def test_available_versions(self, auth_client: TestClient) -> None:
        data = auth_client.get("/api").json()
        assert "v1" in data["available_versions"]
        assert data["available_versions"]["v1"] == API_V1_PATH_PREFIX

    def test_returns_401_without_auth(self, unauth_client: TestClient) -> None:
        response = unauth_client.get("/api")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1 — authenticated endpoint listing
# ---------------------------------------------------------------------------


class TestApiV1Root:
    """GET /api/v1 requires auth and lists available v1 endpoints."""

    def test_returns_200(self, auth_client: TestClient) -> None:
        response = auth_client.get(API_V1_PATH_PREFIX)
        assert response.status_code == 200

    def test_returns_dict(self, auth_client: TestClient) -> None:
        data = auth_client.get(API_V1_PATH_PREFIX).json()
        assert isinstance(data, dict)

    def test_excludes_self(self, auth_client: TestClient) -> None:
        data = auth_client.get(API_V1_PATH_PREFIX).json()
        assert "api_v1_root" not in data

    def test_all_paths_under_v1(self, auth_client: TestClient) -> None:
        data = auth_client.get(API_V1_PATH_PREFIX).json()
        for path in data.values():
            assert path.startswith(API_V1_PATH_PREFIX), f"Path {path} not under {API_V1_PATH_PREFIX}"

    def test_returns_401_without_auth(self, unauth_client: TestClient) -> None:
        response = unauth_client.get(API_V1_PATH_PREFIX)
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/version — authenticated version details
# ---------------------------------------------------------------------------


class TestApiV1Version:
    """GET /api/v1/version requires auth and returns version details."""

    def test_returns_200_with_auth(self, auth_client: TestClient) -> None:
        response = auth_client.get(f"{API_V1_PATH_PREFIX}/version")
        assert response.status_code == 200

    def test_api_version(self, auth_client: TestClient) -> None:
        data = auth_client.get(f"{API_V1_PATH_PREFIX}/version").json()
        assert data["api_version"] == "v1"

    def test_info_version(self, auth_client: TestClient) -> None:
        data = auth_client.get(f"{API_V1_PATH_PREFIX}/version").json()
        assert data["info_version"] == API_V1_VERSION

    def test_status(self, auth_client: TestClient) -> None:
        data = auth_client.get(f"{API_V1_PATH_PREFIX}/version").json()
        assert data["status"] == "current"

    def test_links_null_when_docs_disabled(self, auth_client: TestClient) -> None:
        import syntara.api.main as main_module

        original = main_module._settings.enable_api_docs
        object.__setattr__(main_module._settings, "enable_api_docs", False)
        try:
            data = auth_client.get(f"{API_V1_PATH_PREFIX}/version").json()
            assert data["links"] is None
        finally:
            object.__setattr__(main_module._settings, "enable_api_docs", original)

    def test_links_present_when_docs_enabled(self, auth_client: TestClient) -> None:
        import syntara.api.main as main_module

        original = main_module._settings.enable_api_docs
        object.__setattr__(main_module._settings, "enable_api_docs", True)
        try:
            data = auth_client.get(f"{API_V1_PATH_PREFIX}/version").json()
            assert data["links"] is not None
            assert data["links"]["docs"] == f"{API_DOCS_V1_PATH_PREFIX}/docs"
            assert data["links"]["redoc"] == f"{API_DOCS_V1_PATH_PREFIX}/redoc"
            assert data["links"]["openapi"] == f"{API_DOCS_V1_PATH_PREFIX}/openapi.json"
        finally:
            object.__setattr__(main_module._settings, "enable_api_docs", original)

    def test_returns_401_without_auth(self, unauth_client: TestClient) -> None:
        response = unauth_client.get(f"{API_V1_PATH_PREFIX}/version")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Docs endpoints — unauthenticated at /api_docs/v1/ (when docs enabled)
# ---------------------------------------------------------------------------


class TestDocsNoAuth:
    """Doc endpoints at /api_docs/v1/ are accessible without authentication."""

    @pytest.fixture
    def docs_enabled_client(self) -> Generator[TestClient, None, None]:
        import importlib

        import syntara.api.main as main_module
        from syntara.core.config.base import get_settings

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("APP_ENABLE_API_DOCS", "true")
        get_settings.cache_clear()
        try:
            importlib.reload(main_module)
            yield TestClient(main_module.app, raise_server_exceptions=False)
        finally:
            monkeypatch.delenv("APP_ENABLE_API_DOCS", raising=False)
            get_settings.cache_clear()
            importlib.reload(main_module)

    def test_docs_returns_200_without_auth(self, docs_enabled_client: TestClient) -> None:
        response = docs_enabled_client.get(f"{API_DOCS_V1_PATH_PREFIX}/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_redoc_returns_200_without_auth(self, docs_enabled_client: TestClient) -> None:
        response = docs_enabled_client.get(f"{API_DOCS_V1_PATH_PREFIX}/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_openapi_json_returns_200_without_auth(self, docs_enabled_client: TestClient) -> None:
        response = docs_enabled_client.get(f"{API_DOCS_V1_PATH_PREFIX}/openapi.json")
        assert response.status_code == 200
        assert "openapi" in response.json()

    def test_docs_redirect_from_root(self, docs_enabled_client: TestClient) -> None:
        response = docs_enabled_client.get("/docs", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == f"{API_DOCS_V1_PATH_PREFIX}/docs"


# ---------------------------------------------------------------------------
# api_v1_root with included routers
# ---------------------------------------------------------------------------


class TestApiV1RootWithIncludedRouters:
    """GET /api/v1 correctly lists routes from included routers."""

    @pytest.fixture
    def client_with_router(self) -> Generator[TestClient, None, None]:
        from fastapi import APIRouter

        from syntara.api.main import app
        from syntara.auth.dependencies import get_current_user
        from syntara.core.models.user import User

        async def mock_user() -> User:
            return User(username="testuser", email="test@test.com", first_name="Test")

        original_routes = list(app.routes)
        router = APIRouter()

        @router.get("/test-included")
        async def test_included() -> dict[str, str]:
            return {}

        app.include_router(router, prefix=API_V1_PATH_PREFIX)
        app.dependency_overrides[get_current_user] = mock_user
        client = TestClient(app, raise_server_exceptions=False)
        yield client
        app.dependency_overrides.pop(get_current_user, None)
        app.routes[:] = original_routes

    def test_included_router_routes_appear(self, client_with_router: TestClient) -> None:
        data = client_with_router.get(API_V1_PATH_PREFIX).json()
        assert "test_included" in data
        assert data["test_included"] == f"{API_V1_PATH_PREFIX}/test-included"


# ---------------------------------------------------------------------------
# Old root-level and /api/v1 doc paths are gone (except /docs which redirects)
# ---------------------------------------------------------------------------


class TestOldDocsEndpointsRemoved:
    """Old doc paths under / and /api/v1 must return 404."""

    @pytest.fixture
    def client(self) -> TestClient:
        from syntara.api.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_docs_redirect_404_when_disabled(self) -> None:
        import importlib

        import syntara.api.main as main_module
        from syntara.core.config.base import get_settings

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("APP_ENABLE_API_DOCS", "false")
        get_settings.cache_clear()
        try:
            importlib.reload(main_module)
            client = TestClient(main_module.app, raise_server_exceptions=False)
            assert client.get("/docs").status_code == 404
        finally:
            monkeypatch.delenv("APP_ENABLE_API_DOCS", raising=False)
            get_settings.cache_clear()
            importlib.reload(main_module)

    def test_old_redoc_404(self, client: TestClient) -> None:
        assert client.get("/redoc").status_code == 404

    def test_old_openapi_json_404(self, client: TestClient) -> None:
        assert client.get("/openapi.json").status_code == 404

    def test_old_api_v1_docs_404(self, client: TestClient) -> None:
        assert client.get(f"{API_V1_PATH_PREFIX}/docs").status_code == 404

    def test_old_api_v1_redoc_404(self, client: TestClient) -> None:
        assert client.get(f"{API_V1_PATH_PREFIX}/redoc").status_code == 404

    def test_old_api_v1_openapi_json_404(self, client: TestClient) -> None:
        assert client.get(f"{API_V1_PATH_PREFIX}/openapi.json").status_code == 404


# ---------------------------------------------------------------------------
# Old root endpoint is gone
# ---------------------------------------------------------------------------


class TestOldRootEndpointRemoved:
    """GET / no longer exists."""

    @pytest.fixture
    def client(self) -> TestClient:
        from syntara.api.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_root_returns_404(self, client: TestClient) -> None:
        assert client.get("/").status_code == 404
