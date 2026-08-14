"""Main FastAPI application module for Syntara."""

import asyncio
import json
import ssl
import sys
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import structlog
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import text
from temporalio.service import RPCError

import syntara.auth.exceptions  # Side-effect import to trigger exception handler registration
import syntara.identity_providers.exceptions
from syntara.api.constants import API_V1_PATH_PREFIX, API_V1_VERSION
from syntara.audit.lifecycle import start_audit_subsystems, stop_audit_subsystems
from syntara.audit.middleware import AuditMiddleware
from syntara.audit.registration import discover_and_register_all_handlers
from syntara.auth.cert_middleware import ClientCertAuthMiddleware
from syntara.auth.dependencies import get_current_user
from syntara.auth.middleware import StaleTokenMiddleware
from syntara.auth.session.cleanup import get_session_cleanup_worker
from syntara.authz.evaluator import RegoEvaluator
from syntara.authz.exceptions import (  # noqa: F401
    BuiltinProtectionError,
    DefaultProjectProtectionError,
    PolicyNameConflictError,
    PolicyNotFoundError,
    RoleNameConflictError,
    RoleNotFoundError,
)
from syntara.core.config.base import get_settings, validate_encryption_key_at_startup
from syntara.core.database.session import AsyncSessionLocal, engine
from syntara.core.error_handlers import (
    generic_exception_handler,
    integrity_error_handler,
    problem_details_response_map,
    validation_error_handler,
    value_error_handler,
)
from syntara.core.error_handlers import (
    http_exception_handler as core_http_exception_handler,
)
from syntara.core.exception_registry import register_exceptions
from syntara.core.logging.logging import apply_runtime_log_level, build_uvicorn_logging_config
from syntara.core.models.user import User
from syntara.core.router_discovery import _get_lock_file_path, discover_and_register_routers, iter_api_routes
from syntara.core.websocket.manager import get_connection_lifecycle_manager
from syntara.core.websocket.router import build_websocket_router
from syntara.files.health import check_file_storage_health, validate_file_storage_at_startup
from syntara.files.workers.file_cleanup import get_multipart_cleanup_worker
from syntara.metrics.cleanup import get_metrics_cleanup_worker
from syntara.metrics.completion_poller import get_completion_poller
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.internal_api import (
    metrics_store_component_kpis,
    metrics_store_kpis,
    metrics_store_records,
    metrics_store_reset,
    metrics_store_summary,
)
from syntara.metrics.middleware import MetricsMiddleware
from syntara.metrics.openmetrics import openmetrics_endpoint
from syntara.metrics.queue_depth_poller import get_queue_depth_poller
from syntara.rate_limiting.middleware import RateLimitMiddleware
from syntara.rate_limiting.redis_client import RateLimitRedisClient
from syntara.rate_limiting.token_bucket import TokenBucket
from syntara.settings.cache.settings_cache import SettingsCache, set_runtime_settings
from syntara.settings.store import check_catalog_completeness
from syntara.telemetry.client import flush_telemetry, get_telemetry_registry, initialize_telemetry
from syntara.telemetry.periodic_collector import PeriodicCollector
from syntara.workflows.error_handlers import (
    temporal_rpc_error_handler,
)

logger = structlog.stdlib.get_logger(__name__)

# Upper bound on the readiness database probe.  Must stay comfortably below
# the smallest probe ``timeoutSeconds`` the operator configures (3s) so the
# check fails fast instead of outliving the probe that started it.
DB_PROBE_TIMEOUT_SECONDS = 2.0

# How long a probe outcome is reused before the database is queried again.
# Kept below the shortest probe period (5s) so every interval still gets a
# fresh answer, while bursts of near-simultaneous probes collapse into one
# query.
DB_PROBE_CACHE_TTL_SECONDS = 2.0


@dataclass(frozen=True)
class _DbProbeOutcome:
    """A memoised database probe result.

    ``error_detail`` is stored rather than an ``HTTPException`` so each
    caller raises a fresh exception instead of re-raising one shared
    instance, which would accumulate tracebacks across requests.
    """

    expires_at: float
    error_detail: str | None

    def resolve(self) -> str:
        """Return ``"ok"``, or raise the 503 this outcome represents."""
        if self.error_detail is not None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=self.error_detail,
            )
        return "ok"


_db_probe_cache: _DbProbeOutcome | None = None


async def _check_settings_catalog(session_factory: Any = None) -> None:  # noqa: ANN401
    """Verify every catalog setting has been seeded into the database."""
    factory = session_factory or AsyncSessionLocal
    async with factory() as session:
        missing_keys = await check_catalog_completeness(session)
    if missing_keys:
        sorted_keys = ", ".join(sorted(missing_keys))
        logger.error(
            "Runtime settings catalog is out of date",
            missing_count=len(missing_keys),
            missing_keys=sorted_keys,
        )
        msg = (
            f"Cannot start: runtime settings have not been seeded. "
            f"{len(missing_keys)} setting(s) missing from the database.\n"
            f"Missing keys: {sorted_keys}"
        )
        raise RuntimeError(msg)


def _init_rate_limiting(app: FastAPI) -> RateLimitRedisClient:
    """Create rate limiting components and attach them to ``app.state``."""
    redis_client = RateLimitRedisClient()
    redis_client.connect()
    app.state.rate_limit_redis = redis_client
    app.state.rate_limit_token_bucket = TokenBucket(redis_client=redis_client)
    logger.info("Rate limiting components initialized")
    return redis_client


async def _lifespan_startup(app: FastAPI) -> dict[str, Any]:  # noqa: PLR0915
    """Initialize application resources during startup.

    Returns a dict of resources needed for shutdown.
    """
    validate_encryption_key_at_startup()
    await validate_file_storage_at_startup(get_settings())

    # Fail fast if timezone data is missing (AAP-86297: ubi-minimal strips zone files)
    from syntara.workflows.workflow_engine.models.workflow_definition import _get_valid_timezones  # noqa: PLC0415

    _get_valid_timezones()

    # Initialize logging and audit subsystems
    start_audit_subsystems()

    # Register audit/telemetry handlers so domain events are captured
    discover_and_register_all_handlers()

    # Initialise Settings
    settings = get_settings()
    await _check_settings_catalog()

    # Initialize the process-wide settings cache
    runtime_settings = SettingsCache(session_factory=AsyncSessionLocal)
    set_runtime_settings(runtime_settings)

    # Install database metrics event listeners on the main engine.
    from syntara.metrics.database import install_database_metrics  # noqa: PLC0415

    install_database_metrics(engine)

    # Apply runtime log level (overrides the startup static config if a
    # runtime override has been set by an operator).
    await apply_runtime_log_level()

    # Watch for runtime log level changes and start polling
    runtime_settings.start_watching()

    # Discover and register all routers automatically
    if settings.router_discovery_enabled:
        discover_and_register_routers(
            app=app,
            prefix=API_V1_PATH_PREFIX,
            enable_validation=settings.openapi_validation_enabled,
        )
    else:
        logger.warning("Router discovery disabled - no routers will be automatically registered")

    # Register WebSocket router manually (excluded from router discovery)
    # WebSocket routers use AsyncAPI specification instead of OpenAPI,
    # so they're excluded from the OpenAPI-based validation system and
    # registered manually here instead of through router discovery
    ws_router = build_websocket_router()
    app.include_router(ws_router)

    # Build the resource_actions registry by introspecting all registered
    # routes and merging with BUILTIN_POLICIES.  Must run after all routers
    # (including WebSocket) are registered.
    from syntara.authz.resource_actions import build_resource_actions  # noqa: PLC0415

    app.state.resource_actions = build_resource_actions(app)

    authz_evaluator = RegoEvaluator()
    authz_evaluator.start()
    if await authz_evaluator.health():
        logger.info("Authorization evaluator ready")
    else:
        logger.error("Authorization evaluator failed startup healthcheck")
        msg = "Authorization evaluator failed startup healthcheck"
        raise RuntimeError(msg)
    app.state.authz_evaluator = authz_evaluator

    from syntara.authz.engine import init_authz_cache  # noqa: PLC0415

    init_authz_cache(
        enabled=settings.authz_cache_enabled,
        ttl_seconds=settings.authz_cache_ttl_seconds,
        maxsize=settings.authz_cache_maxsize,
    )

    # Initialize telemetry (reads installation ID from database)
    await initialize_telemetry()

    # Start WebSocket connection health monitoring
    lifecycle_manager = get_connection_lifecycle_manager()
    lifecycle_manager.start_monitoring()
    logger.info("WebSocket connection health monitoring started")

    # Initialize periodic analytics collector
    periodic_collector = PeriodicCollector(
        registry=get_telemetry_registry(),
    )

    completion_poller = get_completion_poller()
    completion_poller.start()

    metrics_cleanup_worker = get_metrics_cleanup_worker()
    metrics_cleanup_worker.start()

    queue_depth_poller = get_queue_depth_poller()
    queue_depth_poller.start()

    session_cleanup_worker = get_session_cleanup_worker()
    session_cleanup_worker.start()

    multipart_cleanup_worker = get_multipart_cleanup_worker()
    multipart_cleanup_worker.start()

    from syntara.workflows.workers.schedule_reconciliation import (  # noqa: PLC0415
        get_schedule_reconciliation_worker,
    )

    schedule_reconciliation_worker = get_schedule_reconciliation_worker()
    schedule_reconciliation_worker.start()

    periodic_collector.start()
    logger.info("Periodic analytics collector started")

    rate_limit_redis = _init_rate_limiting(app)

    return {
        "authz_evaluator": authz_evaluator,
        "lifecycle_manager": lifecycle_manager,
        "periodic_collector": periodic_collector,
        "completion_poller": completion_poller,
        "metrics_cleanup_worker": metrics_cleanup_worker,
        "queue_depth_poller": queue_depth_poller,
        "session_cleanup_worker": session_cleanup_worker,
        "multipart_cleanup_worker": multipart_cleanup_worker,
        "schedule_reconciliation_worker": schedule_reconciliation_worker,
        "runtime_settings": runtime_settings,
        "rate_limit_redis": rate_limit_redis,
    }


async def _lifespan_shutdown(resources: dict[str, Any]) -> None:
    """Clean up application resources during shutdown."""
    await resources["schedule_reconciliation_worker"].stop()
    await resources["multipart_cleanup_worker"].stop()
    await resources["queue_depth_poller"].stop()
    await resources["session_cleanup_worker"].stop()
    await resources["metrics_cleanup_worker"].stop()
    await resources["completion_poller"].stop()

    await resources["periodic_collector"].stop()
    logger.info("Periodic analytics collector stopped")

    flush_telemetry()

    resources["lifecycle_manager"].stop_monitoring()
    logger.info("WebSocket connection health monitoring stopped")

    # Disconnect rate limiting Redis client
    await resources["rate_limit_redis"].disconnect()

    # Stop settings watcher (also disconnects Redis) before disposing DB connections
    await resources["runtime_settings"].stop_watching()

    await resources["authz_evaluator"].stop()

    # Flush and stop audit subsystems before DB dispose so the outbox drain can still query the database
    await stop_audit_subsystems()

    await engine.dispose()
    logger.info("Database engine disposed")

    lock_file = _get_lock_file_path()
    try:
        lock_file.unlink(missing_ok=True)
        logger.debug("Cleaned up lock file", lock_file=lock_file)
    except OSError as e:
        logger.warning("Failed to clean up lock file", lock_file=lock_file, error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:
    """Manage FastAPI application lifespan events.

    Handles initialization and cleanup of application-scoped resources
    like the provider factory.

    Database connections are managed by SQLAlchemy via the get_db() dependency.
    Migrations should be run via Alembic before starting the application:
        uv run alembic upgrade head

    Args:
        app: FastAPI application instance

    Yields:
        None

    """
    resources = await _lifespan_startup(app)
    try:
        yield
    finally:
        await _lifespan_shutdown(resources)


# Swagger UI methods that support "Try it out" when the feature is enabled.
# An empty list disables the button for all operations (Swagger UI config).
_SWAGGER_UI_SUBMIT_METHODS = [
    "get",
    "put",
    "post",
    "delete",
    "options",
    "head",
    "patch",
    "trace",
]


def swagger_ui_parameters(*, enable_try_it_out: bool) -> dict[str, Any]:
    """Build Swagger UI parameters for the FastAPI ``swagger_ui_parameters`` kwarg.

    ``tryItOutEnabled`` only pre-expands the Try it out form. To actually hide
    the interactive execution surface, ``supportedSubmitMethods`` must be an
    empty list when disabled (Swagger UI configuration).
    """
    return {
        "tryItOutEnabled": enable_try_it_out,
        "supportedSubmitMethods": (list(_SWAGGER_UI_SUBMIT_METHODS) if enable_try_it_out else []),
    }


# Create FastAPI application
_settings = get_settings()
app = FastAPI(
    title=f"{_settings.product_name} API",
    description="A distributed multi-agent workflow orchestration system",
    version=API_V1_VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    swagger_ui_parameters=None,
    lifespan=lifespan,
    responses=problem_details_response_map(),
)

# Configure CORS middleware using centralized settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_allow_origins,
    allow_credentials=_settings.cors_allow_credentials,
    allow_methods=_settings.cors_allow_methods,
    allow_headers=_settings.cors_allow_headers,
)

# Register stale token rejection middleware.
app.add_middleware(StaleTokenMiddleware)

# Register rate limiting middleware.
# Executes after AuditMiddleware. Actor identity is resolved by downstream
# auth dependencies (not by the middleware itself). Rate limiting falls back
# to IP-based keys for unauthenticated requests.
# Components are initialised during lifespan and stored on app.state.
app.add_middleware(RateLimitMiddleware, fastapi_app=app)

# Register metrics middleware.
app.add_middleware(MetricsMiddleware, recorder=get_metrics_recorder())

# Register audit middleware.
app.add_middleware(AuditMiddleware, fastapi_app=app)

# Register mTLS client certificate authentication middleware (outermost).
# Must be outermost to access the raw uvicorn transport for cert extraction.
app.add_middleware(ClientCertAuthMiddleware)

# RFC 9457 compliant error handlers
# Import exception modules so @fastapi_exception decorators populate the registry
import syntara.aap.exceptions  # noqa: E402
import syntara.core.storage_exceptions  # noqa: E402
import syntara.credentials.exceptions  # noqa: E402
import syntara.integrations.exceptions  # noqa: E402
import syntara.service_accounts.exceptions  # noqa: E402, F401

# Register decorated exceptions automatically
register_exceptions(app)

# Non-decorated exceptions that still need manual registration
app.add_exception_handler(RPCError, temporal_rpc_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(PydanticValidationError, validation_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(ValueError, value_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(HTTPException, core_http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_exception_handler)

# Routers are automatically discovered and registered via router_discovery system
# See lifespan function above for router registration logic


async def _check_database() -> str:
    """Verify database connectivity, the API's only hard dependency.

    The probe is bounded well below the orchestrator's ``timeoutSeconds``
    so it fails fast rather than piling up.  Without a bound, a saturated
    pool makes the check wait out ``db_pool_timeout_seconds`` (30s by
    default) and a slow-but-alive database hangs it indefinitely — long
    past the point where the kubelet has abandoned the probe.  Each
    abandoned check keeps its place in the pool's FIFO queue, so probes
    accumulate and contend for connections exactly when they are
    scarcest, which is self-amplifying: the pool saturates, readiness
    fails, the replica leaves the Service endpoints, and its load shifts
    onto pods in the same state.

    The session is opened directly rather than via the ``get_db()``
    yield-dependency: driving that generator with ``async for ... break``
    leaves it suspended at its ``yield``, so ``session.close()`` never
    runs and the pooled connection stays checked out until asyncgen
    finalization — on the success path of every probe. ``async with``
    releases it deterministically, which is what makes the bound above
    limit how long the probe *holds* a slot rather than only how long it
    waits for one.

    The outcome is cached for ``DB_PROBE_CACHE_TTL_SECONDS``.  Three probes
    (startup, readiness, and the deprecated ``/health``) can fire within the
    same second, and without a cache each one opens its own connection —
    precisely when the pool is most contended.  Failures are cached too, so
    an outage does not turn every probe into another query against a
    database that is already struggling.  The TTL is short enough that
    recovery is still noticed within one probe interval.

    Returns:
        str: ``"ok"`` when the connectivity probe succeeded.

    Raises:
        HTTPException: 503 when the database is unreachable or too slow.

    """
    # The memo is deliberately process-wide: every probe served by this
    # worker shares it, which is what collapses a burst into one query.
    global _db_probe_cache  # noqa: PLW0603

    cached = _db_probe_cache
    if cached is not None and cached.expires_at > time.monotonic():
        return cached.resolve()

    error_detail: str | None = None
    try:
        async with asyncio.timeout(DB_PROBE_TIMEOUT_SECONDS), AsyncSessionLocal() as session:
            result = await session.exec(text("SELECT 1"))  # type: ignore[call-overload]
            result.scalar()
    except TimeoutError:
        logger.warning(
            "Readiness check failed: database probe timed out",
            timeout_seconds=DB_PROBE_TIMEOUT_SECONDS,
        )
        error_detail = f"Database probe did not complete within {DB_PROBE_TIMEOUT_SECONDS}s"
    except Exception as e:  # noqa: BLE001
        # Any failure at all means "not ready"; a probe has no use for the
        # distinction between one connectivity error and another.
        logger.debug("Readiness check failed: database connectivity error", error=str(e), exc_info=True)
        error_detail = "Database is unreachable"

    _db_probe_cache = _DbProbeOutcome(
        expires_at=time.monotonic() + DB_PROBE_CACHE_TTL_SECONDS,
        error_detail=error_detail,
    )
    return _db_probe_cache.resolve()


@app.get("/health", tags=["Health"], include_in_schema=False, deprecated=True)
async def health_check(request: Request) -> dict[str, Any]:  # noqa: ARG001
    """Health check endpoint with database connectivity test.

    Deprecated: use ``/healthz/live`` for liveness and ``/healthz/ready``
    for readiness.  This endpoint is retained until every consumer (the
    operator's probes in particular) has migrated, and is removed in a
    follow-up change.

    Returns:
        dict: Health status with database status

    Responses:
        200: Service is healthy and database is connected
        503: Database unreachable or too slow. The body is an RFC 9457
            problem document, not the 200 payload shape.

    Example:
        ```bash
        curl http://localhost:8000/health
        ```

        Response:
        ```json
        {
            "status": "healthy",
            "timestamp": "2025-10-09T12:00:00Z",
            "checks": {
                "database": "ok",
                "file_storage": "ok"
            }
        }
        ```

    """
    timestamp = datetime.now(UTC).isoformat()
    db_status = await _check_database()
    file_storage_status = await check_file_storage_health()

    return {
        "status": "healthy",
        "timestamp": timestamp,
        "checks": {
            "database": db_status,
            "file_storage": file_storage_status,
        },
    }


@app.get("/healthz/live", tags=["Health"])
async def liveness_check() -> dict[str, str]:
    """Liveness probe: report whether the process itself is still serving.

    Deliberately checks no backing service.  A liveness failure causes the
    orchestrator to restart the container, so depending on the database
    here would turn a transient database blip into a restart storm across
    every replica.  Dependency health belongs in ``/healthz/ready``.

    Returns:
        dict: Liveness status

    Responses:
        200: The process is alive and able to serve requests

    Example:
        ```bash
        curl http://localhost:8000/healthz/live
        ```

        Response:
        ```json
        {
            "status": "alive",
            "timestamp": "2025-10-09T12:00:00Z"
        }
        ```

    """
    return {
        "status": "alive",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/healthz/ready", tags=["Health"])
async def readiness_check() -> dict[str, Any]:
    """Readiness probe: report whether the API can serve traffic.

    Verifies database connectivity, the API's only hard dependency.  A
    failure removes the pod from the Service endpoints without restarting
    it, so the replica rejoins automatically once the database recovers.

    Object storage is deliberately excluded: it is not a hard dependency,
    since an unconfigured or degraded S3 backend only disables file
    uploads while the rest of the API serves normally.  Its status is
    reported by ``GET /api/v1/files/storage_status`` instead.

    Returns:
        dict: Readiness status with database status

    Responses:
        200: Service is ready and the database is connected
        503: Database unreachable or slower than
            ``DB_PROBE_TIMEOUT_SECONDS``. The body is an RFC 9457 problem
            document, not the 200 payload shape.

    Example:
        ```bash
        curl http://localhost:8000/healthz/ready
        ```

        Response:
        ```json
        {
            "status": "ready",
            "timestamp": "2025-10-09T12:00:00Z",
            "checks": {
                "database": "ok"
            }
        }
        ```

    """
    return {
        "status": "ready",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": {"database": await _check_database()},
    }


app.get("/metrics", tags=["Observability"], include_in_schema=False)(openmetrics_endpoint)


@app.get("/api", tags=["API Discovery"], include_in_schema=False)
async def api_discovery(
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
) -> dict[str, Any]:
    """Return available API versions."""
    return {
        "current_version": API_V1_PATH_PREFIX,
        "available_versions": {
            "v1": API_V1_PATH_PREFIX,
        },
    }


# ---------------------------------------------------------------------------
# API v1 endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1", tags=["API Discovery"], include_in_schema=False)
async def api_v1_root(
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
) -> dict[str, Any]:
    """List available API v1 endpoints."""
    return {
        route.name: route.path
        for route in iter_api_routes(app)
        if route.path.startswith(API_V1_PATH_PREFIX) and route.name != api_v1_root.__name__
    }


@app.get("/api/v1/version", tags=["API Discovery"])
async def api_v1_version(
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
) -> dict[str, Any]:
    """Return full API v1 version details."""
    response: dict[str, Any] = {
        "api_version": "v1",
        "info_version": API_V1_VERSION,
        "status": "current",
        "links": None,
    }

    if _settings.enable_api_docs:
        response["links"] = {
            "docs": f"{API_V1_PATH_PREFIX}/docs",
            "redoc": f"{API_V1_PATH_PREFIX}/redoc",
            "openapi": f"{API_V1_PATH_PREFIX}/openapi.json",
        }

    return response


if _settings.enable_api_docs:
    api_v1_openapi_path = f"{API_V1_PATH_PREFIX}/openapi.json"

    @app.get(f"{API_V1_PATH_PREFIX}/docs", tags=["API Docs"], include_in_schema=False)
    async def api_v1_docs(
        current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    ) -> HTMLResponse:
        """Serve the Swagger UI for API v1."""
        return get_swagger_ui_html(
            openapi_url=api_v1_openapi_path,
            title=f"{app.title} V1 - Docs",
            swagger_ui_parameters=swagger_ui_parameters(
                enable_try_it_out=_settings.enable_try_it_out,
            ),
        )

    @app.get(f"{API_V1_PATH_PREFIX}/redoc", tags=["API Docs"], include_in_schema=False)
    async def api_v1_redoc(
        current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    ) -> HTMLResponse:
        """Serve the ReDoc UI for API v1."""
        return get_redoc_html(openapi_url=api_v1_openapi_path, title=f"{app.title} V1 - ReDoc")

    @app.get(api_v1_openapi_path, tags=["API Docs"], include_in_schema=False)
    async def api_v1_openapi(
        current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    ) -> dict[str, Any]:
        """Return the OpenAPI spec for API v1."""
        return app.openapi()


# ---------------------------------------------------------------------------
# Internal metrics-store endpoints (perf-testing only)
# ---------------------------------------------------------------------------
# Routes are always registered but hidden from OpenAPI.
# Access is gated at runtime by the ``metrics.perf_test_mode`` runtime setting.
_INTERNAL_METRICS_PREFIX = "/_internal/metrics"
app.get(f"{_INTERNAL_METRICS_PREFIX}/summary", include_in_schema=False)(metrics_store_summary)
app.get(f"{_INTERNAL_METRICS_PREFIX}/records", include_in_schema=False)(metrics_store_records)
app.get(f"{_INTERNAL_METRICS_PREFIX}/kpis", include_in_schema=False)(metrics_store_kpis)
app.get(f"{_INTERNAL_METRICS_PREFIX}/kpis/{{component}}", include_in_schema=False)(
    metrics_store_component_kpis,
)
app.post(f"{_INTERNAL_METRICS_PREFIX}/reset", include_in_schema=False)(metrics_store_reset)


def _ssl_context_factory(
    config: uvicorn.Config,  # noqa: ARG001
    default_ssl_context_factory: Any,  # noqa: ANN401 - Callable[[], ssl.SSLContext]
) -> ssl.SSLContext:
    """Build SSL context with TLS 1.3 minimum for Uvicorn server.

    Called by Uvicorn when S2S TLS is enabled. Wraps the default context
    factory to inject minimum_version.
    """
    ctx: ssl.SSLContext = default_ssl_context_factory()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    return ctx


def main() -> None:
    """Entry point for running the application with uvicorn.

    This function is called when the module is run directly.
    For development, you can also use:
        uvicorn syntara.api.main:app --reload
    """
    # Initially configure using the 'fallback_log_level' from static settings.
    # This is necessary so that we can send log messages before the database
    # is available. Once the app starts and database-backed runtime settings are
    # available, the logger will be reconfigured to use the runtime logging.log_level setting.
    settings = get_settings()
    fallback_log_level = settings.fallback_log_level
    uvicorn_kwargs: dict[str, Any] = {
        "app": "syntara.api.main:app",
        "host": settings.server_host,
        "port": settings.server_port,
        "reload": settings.server_reload,
        "log_config": build_uvicorn_logging_config(fallback_log_level),
        "log_level": fallback_log_level.lower(),
    }

    if settings.s2s_tls_enabled:
        uvicorn_kwargs["ssl_certfile"] = settings.s2s_tls_cert_path
        uvicorn_kwargs["ssl_keyfile"] = settings.s2s_tls_key_path
        uvicorn_kwargs["ssl_ca_certs"] = settings.s2s_tls_ca_cert_path
        # CERT_OPTIONAL for local dev; the operator overrides to CERT_REQUIRED
        # via --ssl-cert-reqs 2 in production where all clients present certs.
        uvicorn_kwargs["ssl_cert_reqs"] = ssl.CERT_OPTIONAL
        uvicorn_kwargs["ssl_context_factory"] = _ssl_context_factory
        uvicorn_kwargs["http"] = "syntara.core.tls.protocol:TLSAutoProtocol"

    uvicorn.run(**uvicorn_kwargs)


# Export OpenAPI spec for documentation generation
def export_openapi() -> None:
    """Export OpenAPI specification to JSON file.

    This function is used to generate the OpenAPI spec for documentation.
    Run with: python -m syntara.api.main --export-openapi
    """
    spec = app.openapi()
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    openapi_path = docs_dir / "openapi.json"
    with openapi_path.open("w") as f:
        json.dump(spec, f, indent=2)

    print(f"OpenAPI specification exported to {openapi_path}")  # noqa: T201


if __name__ == "__main__":
    # Check for --export-openapi flag
    if "--export-openapi" in sys.argv:
        export_openapi()
    else:
        main()
