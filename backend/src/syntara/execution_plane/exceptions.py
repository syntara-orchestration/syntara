"""Request failures that prevent deleting AO owners before EP acknowledges intent."""

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response
from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


@fastapi_exception(handler="syntara.execution_plane.exceptions.deletion_error_handler")
class ExecutionPlaneDeletionError(SyntaraError):
    """The owner must be retained because EP deletion intent was not acknowledged."""

    def __init__(self, message: str = "Execution Plane did not acknowledge deletion") -> None:
        """Describe the failed prerequisite for deleting the AO owner."""
        super().__init__(message)


def deletion_error_handler(request: Request, exc: ExecutionPlaneDeletionError) -> JSONResponse:
    """Report the upstream failure without claiming that AO deletion succeeded."""
    return create_problem_details_response(
        status_code=503,
        problem_type=PROBLEM_TYPES["service_unavailable"],
        title="Execution Plane Unavailable",
        detail=str(exc),
        code="EXECUTION_PLANE_DELETION_UNAVAILABLE",
        retryable=True,
        instance=str(request.url),
    )
