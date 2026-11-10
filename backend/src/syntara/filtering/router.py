"""Authenticated, transport-neutral CEL tests with content-free diagnostics."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from syntara.auth import get_current_user
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.exceptions import FilterValidationError
from syntara.filtering.models.result import FilterResult
from syntara.filtering.models.test_request import FilterTestRequest
from syntara.filtering.models.validation_problem import FilterValidationProblem


class _FilterTestRoute(APIRoute):
    """Remove submitted values and field names from validation error diagnostics."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Sanitize before application-level validation handlers log the exception."""
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except FilterValidationError as exc:
                problem = FilterValidationProblem(
                    type="https://api.example.com/errors/validation-error",
                    title="Invalid CEL filter expression",
                    detail=exc.code.value,
                    code=exc.code.value,
                    retryable=False,
                    line=exc.line,
                    column=exc.column,
                )
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content=problem.to_dict(),
                    media_type="application/problem+json",
                )
            except RequestValidationError as exc:
                errors: list[dict[str, object]] = []
                for error in exc.errors():
                    location = error.get("loc", ())
                    field = location[1] if len(location) > 1 and location[1] in {"expression", "input"} else None
                    cause = error.get("ctx", {}).get("error")
                    message = (
                        "Field is required" if error.get("type") == "missing" else "Invalid CEL filter test request"
                    )
                    if isinstance(cause, FilterValidationError):
                        message = cause.code.value
                    errors.append(
                        {"type": "value_error", "loc": ("body", field) if field else ("body",), "msg": message}
                    )
                raise RequestValidationError(errors) from None

        return handler


router = SyntaraRouter(
    prefix="/filtering",
    tags=["Filtering"],
    route_class=_FilterTestRoute,
)


@router.post(
    "/test",
    operation_id="test_cel_filter",
    summary="Test a CEL filter expression",
    dependencies=[NO_PERMISSION, Depends(get_current_user)],
    responses={422: {"model": FilterValidationProblem, "description": "Invalid request or CEL expression"}},
)
def test_cel_filter(body: FilterTestRequest) -> FilterResult:
    """Evaluate caller-supplied JSON with the shared CEL evaluator.

    Authentication is required; no stored resources are read or changed.
    Invalid CEL returns 422. Evaluation returns match, no_match or evaluation_error.
    """
    return PreparedFilter(body.expression).evaluate(body.input)
