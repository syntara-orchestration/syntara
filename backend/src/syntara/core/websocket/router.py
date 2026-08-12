"""WebSocket router for dynamic endpoint registration.

This module provides the WebSocket router that automatically discovers and registers
WebSocket endpoints based on AsyncAPI specifications and handler modules.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import APIRouter

from syntara.core.websocket.endpoint_factory import create_websocket_endpoint, scan_handler_specs
from syntara.core.websocket.interceptor import InterceptorRegistry, ValidationInterceptor, get_registry

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class EndpointRegistrationResult:
    """Result of endpoint registration attempt."""

    success_count: int = 0
    failure_count: int = 0
    total_endpoints: int = field(init=False)

    def __post_init__(self) -> None:
        """Calculate total endpoints after initialization."""
        self.total_endpoints = self.success_count + self.failure_count


def _register_channel_endpoint(
    router: APIRouter,
    component_name: str,
    channel_name: str,
    channel_def: dict[str, Any],
    spec_data: dict[str, Any],
    interceptor_registry: InterceptorRegistry,
) -> bool:
    """Register a single WebSocket channel endpoint.

    Args:
        router: FastAPI router to register endpoint on
        component_name: Name of the component
        channel_name: Name of the channel
        channel_def: Channel definition from spec
        spec_data: Full spec data
        interceptor_registry: Registry for interceptor callbacks

    Returns:
        True if registration succeeded, False otherwise

    """
    address = channel_def.get("address")
    if not address:
        logger.warning("Channel has no address, skipping", channel_name=channel_name)
        return False

    interceptor_registry.before_endpoint_creation(component_name, channel_name, channel_def)

    try:
        endpoint = create_websocket_endpoint(channel_name, spec_data, component_name)
        router.add_websocket_route(address, endpoint)
        logger.info("Registered WebSocket endpoint", address=address, channel_name=channel_name)
        interceptor_registry.after_endpoint_creation(component_name, channel_name, endpoint, success=True)
        return True
    except Exception as e:
        logger.exception("Failed to create endpoint for channel", channel_name=channel_name)
        interceptor_registry.after_endpoint_creation(component_name, channel_name, None, success=False, error=e)
        return False


def _register_spec_endpoints(
    router: APIRouter,
    component_name: str,
    spec_data: dict[str, Any],
    interceptor_registry: InterceptorRegistry,
) -> EndpointRegistrationResult:
    """Register all endpoints for a single spec.

    Args:
        router: FastAPI router to register endpoints on
        component_name: Name of the component
        spec_data: Spec data containing channels
        interceptor_registry: Registry for interceptor callbacks

    Returns:
        Registration result with success/failure counts

    """
    result = EndpointRegistrationResult()
    channels = spec_data.get("channels", {})

    for channel_name, channel_def in channels.items():
        if _register_channel_endpoint(
            router, component_name, channel_name, channel_def, spec_data, interceptor_registry
        ):
            result.success_count += 1
        else:
            result.failure_count += 1

    return result


def build_websocket_router() -> APIRouter:
    """Build an APIRouter with all WebSocket endpoints.

    This function creates a FastAPI router with WebSocket endpoints dynamically
    generated from AsyncAPI specifications using auto-discovery.

    Auto-discovery uses convention-based path mapping:
    src/syntara/{component}/ws/{handler}.py -> schemas/{component}/websocket-{handler}.yaml

    Fail-fast validation ensures:
    - Every handler file has a corresponding spec file
    - Every spec file has a corresponding handler file

    Interceptors are used to validate channel mappings and can be extended
    for additional bootstrap-time checks.

    Returns:
        Configured APIRouter with all WebSocket endpoints

    Raises:
        ValueError: If handler/spec pairing is incomplete

    Examples:
        >>> router = build_websocket_router()
        >>> app.include_router(router)

    """
    router = APIRouter(tags=["WebSocket"])

    # Get the global interceptor registry
    interceptor_registry = get_registry()
    validation_interceptor = ValidationInterceptor()
    interceptor_registry.register(validation_interceptor)

    # Auto-discovery mode: scan handlers (returns dict[component_name, spec_dict])
    specs_by_component = scan_handler_specs()

    if not specs_by_component:
        logger.warning("No WebSocket handlers found. WebSocket endpoints not registered.")
        return router

    # Notify interceptors that bootstrap is starting
    interceptor_registry.on_bootstrap_start(specs_by_component)

    # Register endpoints for all specs
    total_success = 0
    total_failure = 0

    for component_name, spec_data in specs_by_component.items():
        result = _register_spec_endpoints(router, component_name, spec_data, interceptor_registry)
        total_success += result.success_count
        total_failure += result.failure_count

    # Notify interceptors that bootstrap is complete
    bootstrap_results = {
        "total_endpoints": total_success,
        "success_count": total_success,
        "failure_count": total_failure,
        "specs_processed": len(specs_by_component),
    }
    interceptor_registry.on_bootstrap_complete(bootstrap_results)

    logger.info("Registered WebSocket endpoints", endpoint_count=total_success)
    return router
