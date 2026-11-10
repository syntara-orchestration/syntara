"""Filter inputs stay private across dependency logs, OTEL and native regex errors."""

import logging
from collections.abc import Generator
from io import StringIO

import pytest

from syntara.core.logging import logging as module
from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.exceptions import FilterValidationError
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome


@pytest.fixture
def configured_logging(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> Generator[StringIO, None, None]:
    """Start capture before handlers bind stderr; restore logger state afterward."""
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    cel_logger = logging.getLogger("cel_expr_python")
    previous_cel_handlers = cel_logger.handlers[:]
    previous_cel_propagate = cel_logger.propagate
    uvicorn_levels = {name: logging.getLogger(name).level for name in module._UVICORN_LOGGER_NAMES}
    otel_output = StringIO()
    otel_handler = logging.StreamHandler(otel_output)
    monkeypatch.setattr(module, "create_otel_handler", lambda: otel_handler)
    try:
        module.configure_app_logging()
        module._set_log_level("DEBUG")
        yield otel_output
    finally:
        for handler in root.handlers[:]:
            if handler not in previous_handlers:
                handler.close()
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)
        for handler in cel_logger.handlers[:]:
            if handler not in previous_cel_handlers:
                handler.close()
        cel_logger.handlers[:] = previous_cel_handlers
        cel_logger.propagate = previous_cel_propagate
        for name, level in uvicorn_levels.items():
            logging.getLogger(name).setLevel(level)


def test_debug_logging_excludes_real_evaluator_values(configured_logging: StringIO, capfd) -> None:
    private_marker = "private-filter-message-content"
    prepared = PreparedFilter("input.secret + 1 == 2")
    result = prepared.evaluate({"secret": private_marker})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE
    logging.getLogger("cel_expr_python.Evaluator").error("Unsafe dependency diagnostic: %s", private_marker)
    logging.getLogger("syntara.filtering").warning("filter_wrong_type")
    captured = capfd.readouterr()
    assert private_marker not in captured.out + captured.err
    assert private_marker not in configured_logging.getvalue()
    assert "filter_wrong_type" in captured.out + captured.err
    assert "filter_wrong_type" in configured_logging.getvalue()


@pytest.mark.parametrize(
    "logger_name", ["cel_expr_python", "cel_expr_python.Evaluator", "cel_expr_python.future.child"]
)
@pytest.mark.parametrize("level", [logging.DEBUG, logging.ERROR, logging.CRITICAL])
def test_later_root_handler_cannot_receive_cel_inputs(
    configured_logging: StringIO, capfd: pytest.CaptureFixture[str], logger_name: str, level: int
) -> None:
    private_marker = "private-late-handler-content"
    late_output = StringIO()
    late_handler = logging.StreamHandler(late_output)
    assert not late_handler.filters
    root = logging.getLogger()
    root.addHandler(late_handler)
    dependency_logger = logging.getLogger(logger_name)
    previous_level = dependency_logger.level
    try:
        dependency_logger.setLevel(logging.DEBUG)
        result = PreparedFilter("input.secret + 1 == 2").evaluate({"secret": private_marker})
        assert result.error_code == FilterErrorCode.WRONG_TYPE
        dependency_logger.log(level, "Unsafe dependency diagnostic: %s", private_marker)
        logging.getLogger("syntara.filtering").warning("filter_wrong_type")
        captured = capfd.readouterr()
        assert private_marker not in captured.out + captured.err
        assert private_marker not in configured_logging.getvalue()
        assert private_marker not in late_output.getvalue()
        assert "filter_wrong_type" in late_output.getvalue()
    finally:
        dependency_logger.setLevel(previous_level)
        root.removeHandler(late_handler)
        late_handler.close()


def test_invalid_regex_does_not_print_pattern_or_input(configured_logging: StringIO, capfd) -> None:
    private_marker = "private-filter-regex-content"
    result = PreparedFilter("input.text.matches(input.pattern)").evaluate(
        {"text": private_marker, "pattern": private_marker + "["}
    )
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.EVALUATION_FAILED
    captured = capfd.readouterr()
    assert private_marker not in captured.out + captured.err
    assert private_marker not in configured_logging.getvalue()


def test_invalid_configuration_does_not_log_expression(configured_logging: StringIO, capfd) -> None:
    private_marker = "private-filter-expression-content"
    with pytest.raises(FilterValidationError):
        PreparedFilter(f'unknown("{private_marker}")')
    captured = capfd.readouterr()
    assert private_marker not in captured.out + captured.err
    assert private_marker not in configured_logging.getvalue()


def test_uvicorn_reconfiguration_keeps_dependency_filter() -> None:
    config = module.build_uvicorn_logging_config("DEBUG")
    filter_name = "exclude_cel_diagnostics"
    assert config["filters"][filter_name]["()"] == "syntara.core.logging.logging.ExcludeCELDiagnostics"
    assert filter_name in config["handlers"]["syntara"]["filters"]
    assert "syntara" in config["root"]["handlers"]
    assert config["loggers"]["cel_expr_python"]["propagate"] is False
    assert config["loggers"]["cel_expr_python"]["handlers"] == ["discard_cel_diagnostics"]
    assert config["handlers"]["discard_cel_diagnostics"]["class"] == "logging.NullHandler"
