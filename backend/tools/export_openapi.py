"""Export OpenAPI specification without starting the server.

Creates a lightweight FastAPI app, discovers and registers all routers,
then exports the combined OpenAPI JSON or YAML spec. No database or external
services are required.

Usage:
    uv run python tools/export_openapi.py [--output PATH] [--format {json,yaml}]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

from syntara.api.constants import API_V1_PATH_PREFIX, API_V1_VERSION
from syntara.core.error_handlers import apply_rfc9457_media_types, problem_details_response_map
from syntara.core.logging.logging import configure_app_logging
from syntara.core.router_discovery import discover_and_register_routers
from syntara.metrics.internal_api import (
    metrics_store_component_kpis,
    metrics_store_kpis,
    metrics_store_records,
    metrics_store_reset,
    metrics_store_summary,
)


def _extract_route_permission(route: object) -> dict[str, object] | None:
    """Extract x-app-permission dict from a route's dependencies, or None."""
    from syntara.authz.dependencies import PermissionChecker, ProjectScopeFilter, VisibilityFilter
    from syntara.authz.resource_actions import _get_dep_instance, _iter_route_deps

    for dep in _iter_route_deps(route):
        inner = _get_dep_instance(dep)
        if isinstance(inner, (PermissionChecker, ProjectScopeFilter, VisibilityFilter)):
            return {"resource": inner.resource_type, "action": inner.action}
    return None


def _inject_permission_metadata(app: FastAPI, spec: dict[str, Any]) -> None:
    """Add x-app-permission to spec operations from PermissionChecker deps.

    Walks the assembled FastAPI routes, extracts PermissionChecker and
    ProjectScopeFilter instances, and injects x-app-permission into the
    corresponding spec operations.  This makes the exported spec include
    permission metadata derived from runtime code, enabling the drift
    checker to catch mismatches between code and hand-written sub-specs.
    """
    from syntara.core.router_discovery import iter_api_routes

    paths = spec.get("paths", {})
    for route in iter_api_routes(app):
        permission = _extract_route_permission(route)
        if permission is None:
            permission = {"resource": None, "action": None}

        path = route.path
        if path not in paths:
            continue

        for method in route.methods or []:
            method_lower = method.lower()
            if method_lower in paths[path]:
                paths[path][method_lower]["x-app-permission"] = permission


def _rewrite_refs(obj: Any, mapping: dict[str, str]) -> Any:
    """Recursively rewrite $ref and discriminator mapping values."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k == "$ref":
                result[k] = mapping.get(v, v)
            elif k == "mapping" and isinstance(v, dict):
                result[k] = {mk: mapping.get(mv, mv) for mk, mv in v.items()}  # type: ignore[assignment]
            else:
                result[k] = _rewrite_refs(v, mapping)
        return result
    if isinstance(obj, list):
        return [_rewrite_refs(item, mapping) for item in obj]
    return obj


def _consolidate_identical_input_output_schemas(spec: dict[str, Any]) -> None:
    """Merge identical Foo-Input/Foo-Output schema pairs into a single Foo schema.

    FastAPI generates separate -Input and -Output schemas when
    separate_input_output_schemas is True (the default). When both
    variants are structurally identical the split is noise — collapse them
    into one schema and rewrite all $ref pointers.

    Runs in passes: merging leaf schemas and rewriting refs may make parent
    schemas identical too (e.g. WorkflowDefinition).
    """
    max_passes = 5
    for _pass in range(max_passes):
        schemas = spec.get("components", {}).get("schemas", {})

        ref_map: dict[str, str] = {}
        merged: list[tuple[str, str, str]] = []
        for name in list(schemas):
            if not name.endswith("-Input"):
                continue
            base = name.removesuffix("-Input")
            output_name = f"{base}-Output"
            if output_name in schemas and schemas[name] == schemas[output_name] and base not in schemas:
                merged.append((base, name, output_name))
                ref_map[f"#/components/schemas/{name}"] = f"#/components/schemas/{base}"
                ref_map[f"#/components/schemas/{output_name}"] = f"#/components/schemas/{base}"

        if not merged:
            break

        for base, input_name, output_name in merged:
            schemas[base] = schemas.pop(input_name)
            del schemas[output_name]

        rewritten = _rewrite_refs(spec, ref_map)
        spec.clear()
        spec.update(rewritten)
    else:
        remaining = [n for n in spec.get("components", {}).get("schemas", {}) if n.endswith(("-Input", "-Output"))]
        if remaining:
            sys.stderr.write(
                f"WARNING: Schema consolidation did not converge after {max_passes} passes. "
                f"Remaining duplicates: {remaining}\n"
            )


def build_spec_app() -> FastAPI:
    """Build a minimal FastAPI app with all routers for spec generation."""
    from syntara.authz.resource_actions import build_resource_actions

    # Configure logging to stderr before router discovery (prevents log output from contaminating stdout YAML)
    configure_app_logging()

    app = FastAPI(
        title="Syntara API",
        description="A distributed multi-agent workflow orchestration system",
        version=API_V1_VERSION,
        servers=[{"url": API_V1_PATH_PREFIX, "description": "API v1"}],
        responses=problem_details_response_map(),
    )

    discover_and_register_routers(
        app=app,
        prefix="",
        enable_validation=False,
    )

    _register_internal_routes(app)

    app.state.resource_actions = build_resource_actions(app)

    return app


# Internal perf-test endpoints are intentionally hidden in the runtime app
# (`include_in_schema=False`) but included here so generated bindings can
# call them in performance harnesses.
_INTERNAL_METRICS_TAG = "Internal Metrics"
_INTERNAL_ROUTES: list[tuple[str, str, str, str, object]] = [
    (
        "get",
        "/_internal/metrics/summary",
        "get_internal_metrics_summary",
        "Metrics store summary",
        metrics_store_summary,
    ),
    (
        "get",
        "/_internal/metrics/records",
        "get_internal_metrics_records",
        "Metrics store records",
        metrics_store_records,
    ),
    ("get", "/_internal/metrics/kpis", "get_internal_metrics_kpis", "Metrics store KPIs", metrics_store_kpis),
    (
        "get",
        "/_internal/metrics/kpis/{component}",
        "get_internal_metrics_component_kpis",
        "Metrics store component KPIs",
        metrics_store_component_kpis,
    ),
    ("post", "/_internal/metrics/reset", "reset_internal_metrics_store", "Metrics store reset", metrics_store_reset),
]


def _register_internal_routes(app: FastAPI) -> None:
    """Register /_internal routes on the spec app via a declarative table."""
    for method, path, operation_id, summary, endpoint in _INTERNAL_ROUTES:
        getattr(app, method)(
            path,
            summary=summary,
            operation_id=operation_id,
            tags=[_INTERNAL_METRICS_TAG],
        )(endpoint)


def main() -> int:
    """Export OpenAPI spec to file or stdout."""
    parser = argparse.ArgumentParser(description="Export OpenAPI specification")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "yaml"],
        default="yaml",
        help="Output format (default: yaml)",
    )
    args = parser.parse_args()

    app = build_spec_app()
    spec = app.openapi()
    apply_rfc9457_media_types(spec)
    _inject_permission_metadata(app, spec)
    _consolidate_identical_input_output_schemas(spec)

    # Strip auth responses from explicitly unauthenticated endpoints
    for path_ops in spec.get("paths", {}).values():
        for op in path_ops.values():
            if isinstance(op, dict) and op.get("security") == []:
                op.get("responses", {}).pop("401", None)
                op.get("responses", {}).pop("403", None)

    if args.format == "yaml":
        content = yaml.dump(spec, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        content = json.dumps(spec, indent=2) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        sys.stderr.write(f"OpenAPI spec exported to {args.output}\n")
    else:
        sys.stdout.write(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
