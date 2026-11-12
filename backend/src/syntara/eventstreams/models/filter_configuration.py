"""The original CEL expression from a Subscribe trigger."""

from typing import TYPE_CHECKING, ClassVar

from pydantic import ConfigDict, Field, PrivateAttr, model_validator
from sqlmodel import SQLModel

from syntara.filtering.constants import EXPRESSION_DESCRIPTION, MAX_EXPRESSION_LENGTH

if TYPE_CHECKING:
    from syntara.filtering.evaluator import PreparedFilter


class FilterConfiguration(SQLModel):
    """One original CEL expression, with no implicit conditions or field grouping.

    Empty or whitespace-only expressions mean no filter. Publication validates
    syntax, names and statically known boolean types; dynamic types are checked
    during evaluation. The original non-empty expression is preserved unchanged.
    """

    expression: str = Field(strict=True, max_length=MAX_EXPRESSION_LENGTH, description=EXPRESSION_DESCRIPTION)
    _prepared: "PreparedFilter | None" = PrivateAttr(default=None)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_program(self) -> "FilterConfiguration":
        """Compile once, retaining the native program only in private memory."""
        from syntara.filtering.evaluator import PreparedFilter  # noqa: PLC0415

        if self._prepared is None:
            super().__setattr__("_prepared", PreparedFilter(self.expression))
        return self

    @property
    def prepared(self) -> "PreparedFilter":
        """Return the native program prepared during configuration validation."""
        if self._prepared is None:
            message = "Filter configuration has not been validated"
            raise ValueError(message)
        return self._prepared


def normalize_filter(value: FilterConfiguration | None) -> FilterConfiguration | None:
    """Persist a cleared editor as null without rewriting non-empty source."""
    return value if value is not None and value.expression.strip() else None
