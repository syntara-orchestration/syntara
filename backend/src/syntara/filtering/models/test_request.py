"""Caller-supplied JSON for the stateless shared CEL test endpoint."""

from typing import ClassVar

from pydantic import ConfigDict, Field, JsonValue
from sqlmodel import SQLModel

from syntara.filtering.constants import EXPRESSION_DESCRIPTION, MAX_EXPRESSION_LENGTH


class FilterTestRequest(SQLModel):
    """An optional CEL expression and required JSON bound directly as input.

    Omitted, empty and whitespace-only expressions mean no filter. No Kafka
    decoding, input restructuring or payload-schema validation is performed.
    """

    expression: str | None = Field(
        default=None, strict=True, repr=False, max_length=MAX_EXPRESSION_LENGTH, description=EXPRESSION_DESCRIPTION
    )
    input: JsonValue = Field(repr=False)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", allow_inf_nan=False)  # type: ignore[assignment]
