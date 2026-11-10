"""Real logging configuration and CEL/RE2 integration in isolated Python processes.

Isolation captures native C++ diagnostics and avoids replacing pytest's
handlers. No collector, broker, database or Temporal connectivity is claimed.
"""

import os
import subprocess
import sys
from textwrap import dedent

import pytest

pytestmark = pytest.mark.integration

_PROBE = r"""
import logging
import logging.config
import sys
from io import StringIO

from syntara.core.logging.logging import (
    _set_log_level,
    build_uvicorn_logging_config,
    configure_app_logging,
)

if sys.argv[1] == "application":
    configure_app_logging()
else:
    logging.config.dictConfig(build_uvicorn_logging_config("INFO"))

late_output = StringIO()
late_handler = logging.StreamHandler(late_output)
assert not late_handler.filters
logging.getLogger().addHandler(late_handler)
_set_log_level("DEBUG")

from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.exceptions import FilterValidationCode, FilterValidationError
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome

secret = "integration-private-message-marker"
pattern = "integration-private-regex-marker["
expression_secret = "integration-private-expression-marker"

wrong_type = PreparedFilter("input.secret + 1 == 2").evaluate({"secret": secret})
assert wrong_type.error_code == FilterErrorCode.WRONG_TYPE

regex_error = PreparedFilter("input.text.matches(input.pattern)").evaluate(
    {"text": secret, "pattern": pattern}
)
assert regex_error.outcome == FilterOutcome.EVALUATION_ERROR
assert regex_error.error_code == FilterErrorCode.EVALUATION_FAILED

resolved = PreparedFilter("true || input.items.exists(item, item.ok)").evaluate(
    {"secret": secret, "items": [{}, {}]}
)
assert resolved.outcome == FilterOutcome.MATCH

try:
    PreparedFilter('unknown("' + expression_secret + '")')
except FilterValidationError as error:
    assert error.code == FilterValidationCode.UNSUPPORTED_FUNCTION
else:
    raise AssertionError("Invalid expression was accepted")

for name in ("cel_expr_python", "cel_expr_python.Evaluator", "cel_expr_python.future.child"):
    dependency_logger = logging.getLogger(name)
    dependency_logger.setLevel(logging.DEBUG)
    for level in (logging.DEBUG, logging.ERROR, logging.CRITICAL):
        dependency_logger.log(level, "Unsafe dependency diagnostic: %s", secret)
logging.getLogger("syntara.filtering.integration").warning("filter_wrong_type")
late_contents = late_output.getvalue()
assert "filter_wrong_type" in late_contents
assert secret not in late_contents
assert pattern not in late_contents
assert expression_secret not in late_contents
print("filtering-integration-ok")
"""


@pytest.mark.parametrize("configuration", ["application", "uvicorn"])
def test_real_logging_setup_keeps_filter_inputs_private(configuration: str) -> None:
    environment = {
        **os.environ,
        "APP_OTEL_ENABLED": "false",
        "APP_LOG_OUTPUT_FORMAT": "json",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and test source, without a shell
        [sys.executable, "-c", dedent(_PROBE), configuration],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=environment,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    assert "filtering-integration-ok" in completed.stdout
    assert "filter_wrong_type" in output
    assert "integration-private-message-marker" not in output
    assert "integration-private-regex-marker" not in output
    assert "integration-private-expression-marker" not in output
