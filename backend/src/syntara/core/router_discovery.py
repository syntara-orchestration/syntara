"""Automatic router discovery and registration system.

This module provides convention-based router discovery that automatically
finds and registers routers from domain directories without manual registration.

Convention:
    - Standard routers: src/syntara/{domain}/router.py or src/syntara/api/v1/{module}.py
    - Routers must export either:
      - A `router` variable (APIRouter instance)
      - A `build_router()` or `build_{module}_router()` function that returns APIRouter

Example:
    from syntara.core.router_discovery import discover_and_register_routers

    app = FastAPI()
    discover_and_register_routers(
        app=app,
        prefix="/api/v1",
        enable_validation=True
    )

"""

import importlib
import os
import tempfile
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, FastAPI
from filelock import FileLock

from syntara.core.config.base import get_settings
from syntara.core.exceptions import SyntaraError
from syntara.core.router import validate_routes

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.stdlib.get_logger("syntara.core.router_discovery")


def _get_lock_file_path() -> Path:
    """Get worker-specific lock file path for pytest-xdist parallel execution.

    Uses the PYTEST_XDIST_WORKER environment variable to create separate
    lock files per worker, eliminating lock contention between workers.

    Returns:
        Path to worker-specific lock file (e.g., /tmp/syntara_router_discovery_gw0.lock)

    """
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
    lock_filename = f"syntara_router_discovery_{worker_id}.lock"
    return Path(tempfile.gettempdir()) / lock_filename


class RouterDiscoveryError(SyntaraError):
    """Error during router discovery or registration."""


class RouterInfo:
    """Information about a discovered router."""

    def __init__(
        self,
        domain: str,
        module_path: str,
        router: APIRouter,
        router_prefix: str,
        source_file: Path,
    ) -> None:
        """Initialize router information.

        Args:
            domain: Domain name extracted from module path
            module_path: Python module path (e.g., 'syntara.api.v1.workflows')
            router: FastAPI router instance
            router_prefix: Prefix of the router implementation
            source_file: Path to the source file

        """
        self.domain = domain
        self.module_path = module_path
        self.router = router
        self.router_prefix = router_prefix
        self.source_file = source_file

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<RouterInfo domain={self.domain} module={self.module_path}>"


def discover_routers(
    base_paths: list[Path],
    exclude_modules: set[str] | None = None,
) -> list[RouterInfo]:
    """Discover all routers in the specified base paths.

    Scans for Python modules that export routers following conventions:
    - Files named router.py in domain directories
    - Python files in api/v1/ directory
    - Modules exporting 'router' attribute or build_*_router() functions

    Args:
        base_paths: List of base directories to scan for routers
        exclude_modules: Set of module names to exclude from discovery

    Returns:
        List of discovered RouterInfo objects

    """
    exclude_modules = exclude_modules or set()
    discovered: list[RouterInfo] = []

    for base_path in base_paths:
        if not base_path.exists():
            logger.warning("Base path does not exist", path=str(base_path))
            continue

        logger.info("Scanning for routers in path", path=str(base_path))

        # Pattern 1: {domain}/router.py files
        _discover_domain_routers(base_path, exclude_modules, discovered)

        # Pattern 2: api/v1/*.py files
        _discover_api_v1_routers(base_path, exclude_modules, discovered)

    logger.info("Discovered router(s)", count=len(discovered))
    return discovered


def _discover_domain_routers(
    base_path: Path,
    exclude_modules: set[str],
    discovered: list[RouterInfo],
) -> None:
    """Discover routers in {domain}/router.py pattern.

    Args:
        base_path: Base directory to scan
        exclude_modules: Set of module names to exclude
        discovered: List to append discovered routers to

    """
    for router_file in base_path.glob("*/*router.py"):
        domain = router_file.parent.name

        if domain in exclude_modules:
            logger.debug("Skipping excluded domain", domain=domain)
            continue

        router_info = _load_router_from_file(router_file, domain, is_api_v1=False)
        if router_info:
            discovered.append(router_info)


def _discover_api_v1_routers(
    base_path: Path,
    exclude_modules: set[str],
    discovered: list[RouterInfo],
) -> None:
    """Discover routers in api/v1/*.py pattern.

    Args:
        base_path: Base directory to scan
        exclude_modules: Set of module names to exclude
        discovered: List to append discovered routers to

    """
    api_v1_path = base_path / "api" / "v1"
    if not api_v1_path.exists():
        return

    for py_file in api_v1_path.glob("*.py"):
        # Skip non-router modules and websocket (websocket uses AsyncAPI, not OpenAPI)
        if py_file.stem in {"__init__", "utils", "websocket"}:
            continue

        domain = py_file.stem

        if domain in exclude_modules:
            logger.debug("Skipping excluded module", module=domain)
            continue

        router_info = _load_router_from_file(py_file, domain, is_api_v1=True)
        if router_info:
            discovered.append(router_info)


def _load_router_from_file(
    file_path: Path,
    domain: str,
    *,
    is_api_v1: bool = False,
) -> RouterInfo | None:
    """Load router from a Python file.

    Args:
        file_path: Path to the Python file
        domain: Domain name for the router
        is_api_v1: Whether this is an api/v1 module (keyword-only)

    Returns:
        RouterInfo if successful, None otherwise

    """
    try:
        # Extract router prefix
        router_prefix = _extract_router_prefix_from_file_path(file_path)

        # Convert file path to module path
        module_path = f"syntara.api.v1.{domain}" if is_api_v1 else f"syntara.{domain}.{router_prefix}router"

        logger.debug("Importing module", module_path=module_path)
        module = importlib.import_module(module_path)

        # Try to get router from module
        router = _extract_router_from_module(module, domain)

        if router is None:
            logger.warning("No router found in module", module_path=module_path)
            return None

        logger.info("Loaded router from module", domain=domain, module_path=module_path)
        return RouterInfo(
            domain=domain,
            module_path=module_path,
            router=router,
            router_prefix=router_prefix,
            source_file=file_path,
        )

    except ImportError:
        logger.exception("Failed to import module for file", file_path=str(file_path))
        return None
    except Exception:
        logger.exception("Error loading router from file", file_path=str(file_path))
        return None


def _extract_router_prefix_from_file_path(file_path: Path) -> str:
    file_name: str = file_path.name
    return file_name.replace("router.py", "")


def _extract_router_from_module(module: object, domain: str) -> APIRouter | None:
    """Extract router from a module.

    Tries multiple strategies:
    1. Direct 'router' attribute
    2. 'build_router()' function
    3. 'build_{domain}_router()' function

    Args:
        module: Python module object
        domain: Domain name for function name patterns

    Returns:
        APIRouter instance or None

    """
    # Strategy 1: Direct router attribute
    if hasattr(module, "router"):
        router = module.router
        if isinstance(router, APIRouter):
            return router

    # Strategy 2: build_router() function
    if hasattr(module, "build_router"):
        builder: Callable[[], APIRouter] = module.build_router
        if callable(builder):
            return builder()

    # Strategy 3: build_{domain}_router() function
    builder_name = f"build_{domain}_router"
    if hasattr(module, builder_name):
        builder = getattr(module, builder_name)
        if callable(builder):
            return builder()

    return None


def register_routers(
    app: FastAPI,
    routers: list[RouterInfo],
    prefix: str = "",
) -> None:
    """Register discovered routers with the FastAPI application.

    Args:
        app: FastAPI application instance
        routers: List of discovered routers to register
        prefix: Common prefix to apply to all routers (e.g., '/api/v1')

    """
    logger.info("Registering router(s) with prefix", count=len(routers), prefix=prefix or "(none)")

    for router_info in routers:
        try:
            app.include_router(router_info.router, prefix=prefix)
            logger.info(
                "Registered router",
                domain=router_info.domain,
                module_path=router_info.module_path,
            )
        except Exception:
            logger.exception(
                "Failed to register router",
                domain=router_info.domain,
            )


def discover_and_register_routers(
    app: FastAPI,
    prefix: str = "",
    *,
    enable_validation: bool = True,
    exclude_modules: set[str] | None = None,
) -> list[RouterInfo]:
    """Discover and register all routers in the application.

    This is the main entry point for automatic router discovery.
    It scans the codebase for routers, validates them if requested,
    and registers them with the FastAPI application.

    Thread-Safety:
        Uses worker-specific file-based locking to prevent race conditions
        during pytest-xdist parallel execution. Each worker gets its own lock file
        to enable true parallel discovery without contention.

    Args:
        app: FastAPI application instance
        prefix: Common URL prefix for all routers (e.g., '/api/v1')
        enable_validation: Whether to enable OpenAPI validation
        exclude_modules: Set of module names to exclude from discovery

    Returns:
        List of discovered and registered routers

    Raises:
        Timeout: If lock cannot be acquired within 30 seconds

    Example:
        >>> from fastapi import FastAPI
        >>> from syntara.core.router_discovery import discover_and_register_routers
        >>>
        >>> app = FastAPI()
        >>> routers = discover_and_register_routers(
        ...     app=app,
        ...     prefix="/api/v1",
        ...     enable_validation=True,
        ...     exclude_modules={"example", "core"},
        ... )

    """
    # Use worker-specific lock file to prevent contention between pytest-xdist workers
    lock_file = _get_lock_file_path()
    lock = FileLock(str(lock_file), timeout=30.0)
    lock_info = str(lock_file)

    with lock:
        logger.info("=" * 80)
        logger.info("Dynamic Router Discovery and Registration")
        logger.info("Lock file", lock_file=lock_info)
        logger.info("=" * 80)

        # Get configuration from settings if not provided
        if exclude_modules is None:
            settings = get_settings()
            exclude_str = settings.router_exclude_modules.strip()
            exclude_modules = {m.strip() for m in exclude_str.split(",") if m.strip()} if exclude_str else set()

        # Determine base paths to scan
        # Start from the syntara package root
        syntara_root = Path(__file__).resolve().parent.parent
        base_paths = [syntara_root]

        logger.info("Base paths", paths=[str(p) for p in base_paths])
        if exclude_modules:
            logger.info("Excluding modules", modules=", ".join(sorted(exclude_modules)))

        # Discover routers
        routers = discover_routers(base_paths, exclude_modules=exclude_modules)

        if not routers:
            logger.warning("No routers discovered!")
            return []

        # Register routers
        register_routers(app, routers, prefix=prefix)

        # Validate if enabled
        if enable_validation:
            _validate_discovered_routers(app, routers)

        logger.info("=" * 80)
        logger.info("Router discovery completed: router(s) registered", count=len(routers))
        logger.info("=" * 80)

        return routers


def _validate_discovered_routers(app: FastAPI, routers: list[RouterInfo]) -> None:
    """Validate discovered routers against OpenAPI schemas.

    Args:
        app: FastAPI application instance
        routers: List of discovered routers

    """
    settings = get_settings()

    if not settings.openapi_validation_enabled:
        logger.info("OpenAPI validation disabled via configuration")
        return

    try:
        # Build list of schema files based on discovered routers
        schema_files = _build_schema_file_list(routers)

        if schema_files:
            logger.info("Validating schema file(s)", count=len(schema_files))
            validate_routes(app, schema_files)
        else:
            logger.info("No schema files found for validation")

    except Exception:
        logger.exception("Error during router validation")


def _build_schema_file_list(routers: list[RouterInfo]) -> list[str]:
    """Build list of schema files from discovered routers.

    Follows convention:
    - Primary router (router.py): schemas/{domain}/openapi.{json|yaml}
    - Sub-router ({prefix}_router.py): schemas/{domain}/{prefix}.openapi.{json|yaml}

    Args:
        routers: List of discovered routers

    Returns:
        List of schema file paths relative to schemas/ directory

    """
    schema_files = []
    # Access schemas from package resources
    schemas_package = files("syntara").joinpath("schemas")

    for router_info in routers:
        domain = router_info.domain
        router_prefix = router_info.router_prefix

        # Build schema filename from router prefix.
        # Primary routers (prefix="") -> openapi.{ext}
        # Sub-routers (prefix="executions_") -> executions.openapi.{ext}
        if router_prefix:
            descriptor = router_prefix.rstrip("_")
            schema_filename_template = f"{descriptor}.openapi.{{ext}}"
        else:
            schema_filename_template = "openapi.{ext}"

        # Check for both JSON and YAML schemas in the primary domain directory
        for ext in ["json", "yaml", "yml"]:
            schema_filename = schema_filename_template.format(ext=ext)
            schema_resource = schemas_package.joinpath(domain).joinpath(schema_filename)
            try:
                if schema_resource.is_file():
                    relative_path = f"{domain}/{schema_filename}"
                    schema_files.append(relative_path)
                    logger.debug("Found schema", path=relative_path)
                    break  # Use first found format
            except (FileNotFoundError, AttributeError):
                # Resource doesn't exist or directory doesn't exist
                continue

    return schema_files


def iter_api_routes(app_or_router: Any) -> Iterator[Any]:  # noqa: ANN401
    """Yield API route objects from a FastAPI app or router.

    FastAPI >=0.135 wraps included routers in ``_IncludedRouter`` objects
    instead of flattening them into ``app.routes``.  This helper walks
    the tree recursively and yields ``_EffectiveRouteContext`` objects
    (which expose ``.path``, ``.methods``, ``.endpoint``, ``.dependant``,
    and ``.dependencies`` — the same attributes as ``APIRoute``).

    For direct ``APIRoute`` entries (e.g. health-check routes added
    without ``include_router``) the original ``APIRoute`` is yielded.
    """
    from fastapi.routing import APIRoute  # noqa: PLC0415

    for route in app_or_router.routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "effective_candidates"):
            for candidate in route.effective_candidates():
                if hasattr(candidate, "methods") and hasattr(candidate, "path"):
                    yield candidate
                elif hasattr(candidate, "effective_candidates"):
                    yield from _walk_included(candidate)


def _walk_included(included: Any) -> Iterator[Any]:  # noqa: ANN401
    """Recursively walk nested _IncludedRouter objects."""
    for candidate in included.effective_candidates():
        if hasattr(candidate, "methods") and hasattr(candidate, "path"):
            yield candidate
        elif hasattr(candidate, "effective_candidates"):
            yield from _walk_included(candidate)


__all__ = [
    "RouterDiscoveryError",
    "RouterInfo",
    "discover_and_register_routers",
    "discover_routers",
    "register_routers",
]
