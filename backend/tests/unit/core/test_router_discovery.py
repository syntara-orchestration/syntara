"""Unit tests for router discovery system."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI

from syntara.core.router_discovery import (
    RouterInfo,
    _extract_router_from_module,
    _extract_router_prefix_from_file_path,
    discover_and_register_routers,
    discover_routers,
    iter_api_routes,
    register_routers,
)


class TestExtractRouterFromModule:
    """Tests for _extract_router_from_module function."""

    def test_extract_direct_router_attribute(self) -> None:
        """Test extracting router from direct 'router' attribute."""
        # Create a mock module with router attribute
        module = MagicMock()
        router = APIRouter()
        module.router = router

        result = _extract_router_from_module(module, "test_domain")

        assert result is router

    def test_extract_from_build_router_function(self) -> None:
        """Test extracting router from build_router() function."""
        # Create a mock module with build_router function
        module = MagicMock()
        router = APIRouter()

        def build_router() -> APIRouter:
            return router

        module.build_router = build_router
        delattr(module, "router")  # Remove router attribute to test function path

        result = _extract_router_from_module(module, "test_domain")

        assert result is router

    def test_extract_from_domain_specific_builder(self) -> None:
        """Test extracting router from build_{domain}_router() function."""
        # Create a mock module with build_workflows_router function
        module = MagicMock()
        router = APIRouter()

        def build_workflows_router() -> APIRouter:
            return router

        module.build_workflows_router = build_workflows_router
        delattr(module, "router")  # Remove router attribute
        delattr(module, "build_router")  # Remove generic builder

        result = _extract_router_from_module(module, "workflows")

        assert result is router


class TestDiscoverRouters:
    """Tests for discover_routers function."""

    def test_discover_excludes_specified_modules(self, tmp_path: Path) -> None:
        """Test that specified modules are excluded from discovery."""
        # Create test directory structure
        test_module_dir = tmp_path / "test_module"
        test_module_dir.mkdir()

        excluded_dir = tmp_path / "excluded"
        excluded_dir.mkdir()

        # Create router files
        (test_module_dir / "router.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()")
        (excluded_dir / "router.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()")

        # Mock the import to avoid actual module loading
        with patch("syntara.core.router_discovery._load_router_from_file") as mock_load:
            mock_load.return_value = None  # Prevent actual loading

            discover_routers(
                base_paths=[tmp_path],
                exclude_modules={"excluded"},
            )

            # Should have called load for test_module but not excluded
            calls = [call[0][0] for call in mock_load.call_args_list]
            assert any("test_module" in str(call) for call in calls)
            assert not any("excluded" in str(call) for call in calls)

    def test_discover_finds_ancillary_routers(self, tmp_path: Path) -> None:
        """Test discovery finds routers with different prefixes."""
        # Create test directory structure with multiple routers
        domain_dir = tmp_path / "test_domain"
        domain_dir.mkdir()

        # Create main and ancillary router files
        (domain_dir / "router.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()")
        (domain_dir / "sub_router.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()")
        (domain_dir / "admin_router.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()")

        with patch("syntara.core.router_discovery._load_router_from_file") as mock_load:
            mock_load.return_value = None

            discover_routers(
                base_paths=[tmp_path],
                exclude_modules=set(),
            )

            # Should find all three router files
            calls = [str(call[0][0]) for call in mock_load.call_args_list]
            assert any("router.py" in call for call in calls)
            assert any("sub_router.py" in call for call in calls)
            assert any("admin_router.py" in call for call in calls)


class TestRegisterRouters:
    """Tests for register_routers function."""

    def test_register_routers_includes_prefix(self) -> None:
        """Test that routers are registered with the specified prefix."""
        app = FastAPI()
        router = APIRouter()

        # Add a test route to the router
        @router.get("/test")
        def test_endpoint() -> dict[str, str]:
            return {"test": "data"}

        router_info = RouterInfo(
            domain="test",
            module_path="syntara.test.router",
            router=router,
            router_prefix="",
            source_file=Path("/test/router.py"),
        )

        register_routers(app, [router_info], prefix="/api/v1")

        # Verify the route was registered with the correct prefix
        route_paths = [route.path for route in iter_api_routes(app)]
        assert "/api/v1/test" in route_paths

    def test_register_handles_exceptions(self) -> None:
        """Test that registration exceptions are logged and don't crash."""
        app = FastAPI()

        # Create a router that will fail on registration
        bad_router = MagicMock()
        bad_router.routes = []

        router_info = RouterInfo(
            domain="bad",
            module_path="syntara.bad.router",
            router=bad_router,
            router_prefix="",
            source_file=Path("/bad/router.py"),
        )

        with (
            patch.object(app, "include_router", side_effect=Exception("Test error")),
            patch("syntara.core.router_discovery.logger") as mock_logger,
        ):
            register_routers(app, [router_info], prefix="/api/v1")

        # Verify logger.exception was called with the expected message
        mock_logger.exception.assert_called_once()
        call_args = mock_logger.exception.call_args
        assert "Failed to register router" in call_args[0][0]
        assert call_args[1]["domain"] == router_info.domain

    def test_static_routes_registered_before_parameterized(self) -> None:
        """Static-prefix routes must be registered before parameterized siblings.

        /groups/directory must be matched before /groups/{group_id},
        otherwise FastAPI routes the request to the parameterized handler.
        """
        app = FastAPI()

        parameterized_router = APIRouter(prefix="/groups")

        @parameterized_router.get("/{group_id}")
        def get_group(group_id: str) -> dict[str, str]:
            return {"id": group_id}

        static_router = APIRouter(prefix="/groups/directory")

        @static_router.get("")
        def list_directory() -> list[dict[str, str]]:
            return [{"id": "1", "name": "admins"}]

        # Pass parameterized first — register_routers should re-order
        routers = [
            RouterInfo(
                domain="users",
                module_path="syntara.users.groups_router",
                router=parameterized_router,
                router_prefix="groups_",
                source_file=Path("/users/groups_router.py"),
            ),
            RouterInfo(
                domain="users",
                module_path="syntara.users.groups_directory_router",
                router=static_router,
                router_prefix="groups_directory_",
                source_file=Path("/users/groups_directory_router.py"),
            ),
        ]

        register_routers(app, routers, prefix="/api/v1")

        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/v1/groups/directory")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "admins"


class TestDiscoverAndRegisterRouters:
    """Tests for discover_and_register_routers function."""

    def test_discover_and_register_uses_configuration(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that function uses configuration from settings."""
        app = FastAPI()

        with (
            patch("syntara.core.router_discovery.discover_routers") as mock_discover,
            patch("syntara.core.router_discovery.register_routers"),
            override_settings(
                router_exclude_modules="core,utils",
                openapi_validation_enabled=False,
            ),
        ):
            mock_discover.return_value = []

            discover_and_register_routers(
                app=app,
                prefix="/api/v1",
                enable_validation=True,
            )

            # Should have passed exclude_modules from config
            exclude_modules = mock_discover.call_args[1]["exclude_modules"]
            assert "core" in exclude_modules
            assert "utils" in exclude_modules

    def test_validation_runs_when_enabled(self) -> None:
        """Test that validation runs when enable_validation is True."""
        app = FastAPI()

        router_info = RouterInfo(
            domain="test",
            module_path="syntara.test.router",
            router=APIRouter(),
            router_prefix="",
            source_file=Path("/test/router.py"),
        )

        with (
            patch("syntara.core.router_discovery.discover_routers") as mock_discover,
            patch("syntara.core.router_discovery.register_routers"),
            patch("syntara.core.router_discovery._validate_discovered_routers") as mock_validate,
        ):
            # Return at least one router so validation is attempted
            mock_discover.return_value = [router_info]

            discover_and_register_routers(
                app=app,
                prefix="/api/v1",
                enable_validation=True,
            )

            # Validation should have been called
            assert mock_validate.called


@pytest.mark.integration
class TestRealRouterDiscovery:
    """Integration tests using real router files."""

    def test_discover_real_routers(self) -> None:
        """Test discovery with real routers in the codebase."""
        # This test uses the actual codebase structure
        syntara_root = Path(__file__).resolve().parent.parent.parent.parent / "src" / "syntara"

        if not syntara_root.exists():
            pytest.skip("Syntara source directory not found")

        routers = discover_routers(
            base_paths=[syntara_root],
            exclude_modules={"websocket", "utils", "constants"},
        )

        # Should discover at least some routers
        assert len(routers) > 0

        # All discovered routers should have valid domains
        for router_info in routers:
            assert router_info.domain
            assert router_info.module_path
            assert isinstance(router_info.router, APIRouter)

    def test_full_discovery_and_registration(self) -> None:
        """Test full discovery and registration flow."""
        app = FastAPI()

        # Use actual router discovery with excludes
        routers = discover_and_register_routers(
            app=app,
            prefix="/api/v1",
            enable_validation=False,  # Disable validation for this test
            exclude_modules={"websocket", "example"},  # Exclude special cases
        )

        # Should have discovered and registered routers
        assert len(routers) > 0

        # App should have routes registered
        # (More routes than just health endpoint)
        assert len(app.routes) > 1


class TestExtractRouterPrefixFromFilePath:
    """Tests for _extract_router_prefix_from_file_path function."""

    @pytest.mark.parametrize(
        ("file_path", "expected_prefix"),
        [
            (Path("domain/router.py"), ""),
            (Path("domain/sub_router.py"), "sub_"),
            (Path("domain/admin_router.py"), "admin_"),
            (Path("workflows/custom_router.py"), "custom_"),
        ],
        ids=["main-router", "sub-router", "admin-router", "custom-router"],
    )
    def test_prefix_extraction(self, file_path: Path, expected_prefix: str) -> None:
        """Test router prefix extraction from file paths."""
        result = _extract_router_prefix_from_file_path(file_path)
        assert result == expected_prefix
