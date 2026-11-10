"""Saved and preview CEL expressions share a pre-compilation product limit."""

from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from syntara.eventstreams.models.filter_configuration import FilterConfiguration
from syntara.filtering import evaluator
from syntara.filtering.constants import MAX_EXPRESSION_LENGTH
from syntara.filtering.models.test_request import FilterTestRequest


@pytest.mark.parametrize("length", [MAX_EXPRESSION_LENGTH - 1, MAX_EXPRESSION_LENGTH])
def test_expression_boundary_is_accepted_without_rewriting_source(monkeypatch, length: int) -> None:
    compile_expression = Mock()
    monkeypatch.setattr(evaluator, "compile_expression", compile_expression)
    expression = " " * (length - 4) + "true"
    assert FilterConfiguration(expression=expression).expression == expression
    assert FilterTestRequest(expression=expression, input={}).expression == expression
    compile_expression.assert_called_once_with(expression)


def test_oversized_expressions_are_rejected_before_compilation(monkeypatch) -> None:
    compile_expression = Mock(side_effect=AssertionError("Oversized source must not reach CEL"))
    monkeypatch.setattr(evaluator, "compile_expression", compile_expression)
    expression = "x" * (MAX_EXPRESSION_LENGTH + 1)
    with pytest.raises(ValidationError):
        FilterConfiguration(expression=expression)
    with pytest.raises(ValidationError):
        FilterTestRequest(expression=expression, input={})
    compile_expression.assert_not_called()


def test_both_request_schemas_publish_the_expression_limit() -> None:
    assert FilterConfiguration.model_json_schema()["properties"]["expression"]["maxLength"] == MAX_EXPRESSION_LENGTH
    variants = FilterTestRequest.model_json_schema()["properties"]["expression"]["anyOf"]
    assert next(variant for variant in variants if variant["type"] == "string")["maxLength"] == MAX_EXPRESSION_LENGTH
