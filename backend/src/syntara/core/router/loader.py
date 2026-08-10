"""OpenAPI schema loading and parsing."""

import json
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog
import yaml

logger = structlog.stdlib.get_logger("syntara.core.router.loader")

JSON_EXTENSION: str = ".json"
YAML_EXTENSION: str = ".yaml"
YML_EXTENSION: str = ".yml"


class EndpointDefinition:
    """Represents a single endpoint from OpenAPI spec."""

    def __init__(
        self,
        path: str,
        method: str,
        operation_id: str,
        parameters: list[dict[str, Any]],
        request_body: dict[str, Any] | None = None,
    ) -> None:
        """Initialize endpoint definition with path, method, and parameters."""
        self.path = path
        self.method = method.lower()
        self.operation_id = operation_id
        self.parameters = parameters or []
        self.request_body = request_body

    @property
    def expected_function_name(self) -> str:
        """Convert operationId to snake_case for function name."""
        # Convert camelCase to snake_case
        result = []
        for i, char in enumerate(self.operation_id):
            if char.isupper() and i > 0 and self.operation_id[i - 1].islower():
                # Add underscore before uppercase letter
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    @property
    def path_parameters(self) -> list[str]:
        """Get list of path parameter names."""
        return [param["name"] for param in self.parameters if param.get("in") == "path"]

    @property
    def query_parameters(self) -> list[str]:
        """Get list of query parameter names."""
        return [param["name"] for param in self.parameters if param.get("in") == "query"]

    @property
    def required_parameters(self) -> list[str]:
        """Get list of required parameter names.

        Per OpenAPI spec, path parameters default to required=true,
        while query/header/cookie parameters default to required=false.
        """
        return [param["name"] for param in self.parameters if param.get("required", param.get("in") == "path")]

    def __repr__(self) -> str:
        """Return string representation of endpoint."""
        return f"<Endpoint {self.method.upper()} {self.path} ({self.operation_id})>"


class OpenAPISchema:
    """Represents a loaded OpenAPI schema."""

    def __init__(self, filename: str, schema_data: dict[str, Any]) -> None:
        """Initialize OpenAPI schema from file data."""
        self.filename = filename
        self.schema_data = schema_data
        self.endpoints: list[EndpointDefinition] = []
        self._parse_endpoints()

    @property
    def domain(self) -> str:
        """Extract domain name from filename.

        Supports multiple patterns:
        - schemas/{domain}.json -> domain is filename stem (e.g., 'example.json' -> 'example')
        - schemas/{domain}.yaml -> domain is filename stem (e.g., 'example.yaml' -> 'example')
        - schemas/{domain}/openapi.{json|yaml|yml} -> domain is parent directory
          (e.g., 'example/openapi.yaml' -> 'example')
        - schemas/{domain}/{descriptor}.openapi.{json|yaml|yml} -> descriptor is domain
          (e.g., 'workflows/v2/executions_openapi.yaml' -> 'executions')
        - schemas/{domain}/{descriptor}_openapi.{json|yaml|yml} -> descriptor is domain
          (e.g., 'workflows/sub_openapi.json' -> 'sub')
        """
        path = Path(self.filename)

        # If filename is 'openapi.{ext}', use parent directory as domain
        if path.stem == "openapi" and path.suffix in {JSON_EXTENSION, YAML_EXTENSION, YML_EXTENSION}:
            return path.parent.name

        # Convention for domain sub-routers: {descriptor}.openapi.{ext} or {descriptor}_openapi.{ext}
        if path.stem.endswith(".openapi") and path.suffix in {JSON_EXTENSION, YAML_EXTENSION, YML_EXTENSION}:
            return path.stem[: -len(".openapi")]
        if path.stem.endswith("_openapi") and path.suffix in {JSON_EXTENSION, YAML_EXTENSION, YML_EXTENSION}:
            return path.stem[: -len("_openapi")]

        # Otherwise, use filename stem as domain
        return path.stem

    @property
    def base_path(self) -> str:
        """Extract common base path from server URLs.

        Finds the longest common path prefix from all defined server URLs.
        If no servers are defined, returns empty string (paths are treated as absolute).

        Returns:
            Common base path (e.g., '/api/v1') or empty string

        Examples:
            - Servers: ['http://localhost:8000/api/v1', 'https://prod.com/api/v1'] -> '/api/v1'
            - Servers: ['http://localhost:8000/api/v1', 'https://prod.com/api/v2'] -> '/api'
            - No servers -> ''

        """
        servers = self.schema_data.get("servers", [])

        if not servers:
            return ""

        # Extract path from each server URL
        paths = []
        for server in servers:
            url = server.get("url", "")
            parsed = urlparse(url)
            path = parsed.path.rstrip("/")  # Remove trailing slash
            paths.append(path)  # Include empty paths too

        # If any server has no path, we can't determine a common base path
        if "" in paths and len(set(paths)) > 1:
            return ""

        # Remove empty paths for comparison
        paths = [p for p in paths if p]

        if not paths:
            return ""

        # Find longest common prefix
        if len(paths) == 1:
            return str(paths[0])

        # Find common prefix by comparing path segments
        common_segments = []
        split_paths = [p.split("/") for p in paths]

        for segments in zip(*split_paths, strict=False):
            if len(set(segments)) == 1:  # All segments are the same
                common_segments.append(segments[0])
            else:
                break

        return "/".join(common_segments)

    def _parse_endpoints(self) -> None:
        """Parse endpoints from OpenAPI paths."""
        paths = self.schema_data.get("paths", {})

        for path, path_item in paths.items():
            # Each path can have multiple methods
            for method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                if method in path_item:
                    operation = path_item[method]
                    operation_id = operation.get("operationId")

                    if not operation_id:
                        logger.warning("Missing operationId", method=method.upper(), path=path, filename=self.filename)
                        continue

                    endpoint = EndpointDefinition(
                        path=path,
                        method=method,
                        operation_id=operation_id,
                        parameters=operation.get("parameters", []),
                        request_body=operation.get("requestBody"),
                    )
                    self.endpoints.append(endpoint)

    def __repr__(self) -> str:
        """Return string representation of schema."""
        return f"<OpenAPISchema {self.filename} ({len(self.endpoints)} endpoints)>"


def load_openapi_schema(filename: str) -> OpenAPISchema | None:
    """Load and parse an OpenAPI schema file from package resources.

    Supports both JSON and YAML formats. The format is detected automatically
    based on the file extension (.json, .yaml, .yml).

    Args:
        filename: Name of the schema file (e.g., 'example.json', 'example/openapi.yaml')

    Returns:
        OpenAPISchema instance or None if loading fails

    """
    try:
        # Access schema files from the package
        schemas_package = files("syntara").joinpath("schemas")
        schema_resource = schemas_package.joinpath(filename)

        if not schema_resource.is_file():
            logger.error("Schema file not found in package", schema_path=f"schemas/{filename}")
            return None

        # Read the file content
        content = schema_resource.read_text(encoding="utf-8")

        # Detect format based on file extension
        suffix = Path(filename).suffix
        if suffix in {YAML_EXTENSION, YML_EXTENSION}:
            schema_data = yaml.safe_load(content)
        elif suffix == JSON_EXTENSION:
            schema_data = json.loads(content)
        else:
            logger.error("Unsupported schema format (use .json, .yaml, or .yml)", format=suffix)
            return None

        schema = OpenAPISchema(filename, schema_data)
        logger.info("Loaded schema", filename=filename, endpoint_count=len(schema.endpoints), domain=schema.domain)
        return schema

    except (FileNotFoundError, json.JSONDecodeError, yaml.YAMLError):
        logger.exception("Error loading schema", filename=filename)
        return None
    except Exception:
        logger.exception("Unexpected error loading", filename=filename)
        return None


def load_schemas(schema_files: list[str]) -> list[OpenAPISchema]:
    """Load multiple OpenAPI schema files.

    Args:
        schema_files: List of schema filenames

    Returns:
        List of successfully loaded OpenAPISchema instances

    """
    schemas = []

    for filename in schema_files:
        schema = load_openapi_schema(filename)
        if schema:
            schemas.append(schema)

    logger.info("Loaded schema files successfully", loaded_count=len(schemas), total_count=len(schema_files))
    return schemas
