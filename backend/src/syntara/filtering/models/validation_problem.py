"""Safe compiler diagnostics using the application's problem-details contract."""

from pydantic import Field

from syntara.core.models.error import ErrorData


class FilterValidationProblem(ErrorData):
    """Invalid CEL with a safe category and optional one-based compiler location."""

    line: int | None = Field(default=None, ge=1, description="One-based compiler source line, when available")
    column: int | None = Field(default=None, ge=1, description="One-based compiler source column, when available")
