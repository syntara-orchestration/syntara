"""Dynamic OpenAPI router validation system."""

import structlog
from fastapi import FastAPI

from .loader import load_schemas
from .validator import RouteValidator, log_validation_errors

logger = structlog.stdlib.get_logger("syntara.core.router")


def validate_routes(app: FastAPI, schema_files: list[str]) -> None:
    """Validate FastAPI routes against OpenAPI schema specifications.

    This function performs comprehensive validation to ensure that:
    - Every OpenAPI endpoint has a corresponding handler implementation
    - Every handler has a corresponding OpenAPI specification
    - Function names match operationId conventions (camelCase -> snake_case)
    - Required parameters are present in function signatures
    - API paths follow the /api/v{version}/{domain} pattern

    Validation errors are logged but do not prevent application startup,
    allowing for iterative development.

    Args:
        app: FastAPI application instance
        schema_files: List of OpenAPI schema filenames relative to schemas/ directory.
                     Supports two patterns:
                     - '{domain}.json' (e.g., 'example.json')
                     - '{domain}/openapi.json' (e.g., 'example/openapi.json')

    Example:
        >>> from fastapi import FastAPI
        >>> from app.core.router import validate_routes
        >>>
        >>> app = FastAPI()
        >>> validate_routes(app, ['example.json'])  # or ['example/openapi.json']

    """
    logger.info("=" * 80)
    logger.info("Dynamic OpenAPI Router Validation")
    logger.info("=" * 80)
    logger.info("Schema files to validate", schema_files=", ".join(schema_files))

    # Load all OpenAPI schemas
    schemas = load_schemas(schema_files)

    if not schemas:
        logger.error("No schemas loaded successfully. Validation aborted.")
        return

    # Perform validation
    validator = RouteValidator(app, schemas)
    errors = validator.validate()

    # Log results
    log_validation_errors(errors)


__all__ = ["validate_routes"]
