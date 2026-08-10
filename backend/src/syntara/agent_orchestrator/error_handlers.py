"""RFC 9457 compliant error handlers for Agent Orchestrator domain.

This module provides error handling for LLM and agent-specific exceptions.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.agent_orchestrator.exceptions import LLMConfigurationError

logger = structlog.stdlib.get_logger(__name__)


def llm_configuration_error_handler(request: Request, exc: "LLMConfigurationError") -> JSONResponse:
    """Handle LLMConfigurationError with RFC 9457 format."""
    logger.error("LLM configuration error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        problem_type=PROBLEM_TYPES["service_unavailable"],
        title="LLM Configuration Error",
        detail="Language model service is not properly configured",
        code="LLM_CONFIGURATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )
