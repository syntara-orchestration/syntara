"""Xfail LLM e2e tests only when OpenRouter actually reports a credit failure.

``@pytest.mark.xfail_openrouter_credits`` is *not* a blanket xfail. The test
runs for real. A failure becomes xfail only when:

* ``GET https://openrouter.ai/api/v1/key`` reports ``limit_remaining <= 0``
  (checked at setup, so we do not wait on a 180s workflow poll), or
* the test's failure text looks like an OpenRouter 402 / insufficient-credits
  error (including Syntara's ``INSUFFICIENT_CREDITS`` classification).

Any other failure (timeouts, script bugs, generic LLM streaming errors) stays
a real failure. A passing test is a pass, not an xpass.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pytest
from orchestrator_test_sdk.e2e.openrouter import OpenRouterStatus, probe_openrouter_key

if TYPE_CHECKING:
    from collections.abc import Generator

    import httpx
    from pluggy import Result

_XFAIL_REASON = "OpenRouter insufficient credits"

# Match credit failures in pytest longrepr. Do not match a bare "402" — that
# appears in line numbers (``file.py:402:``) and must not hide unrelated bugs.
# Quote ``openrouter_credits`` so the marker name ``xfail_openrouter_credits``
# in the traceback does not treat every marked failure as a credit error.
_CREDIT_ERROR_RE = re.compile(
    r"insufficient credits?"
    r"|payment required"
    r"|requires more credits?"
    r"|INSUFFICIENT_CREDITS"
    r"|['\"]openrouter_credits['\"]"
    r"|error code:\s*402"
    r"|http(?:\s+status)?\s*402"
    r"|status(?:\s+code)?\s*402"
    r"|['\"]code['\"]:\s*402",
    re.IGNORECASE,
)

_EXHAUSTED_KEY: pytest.StashKey[bool] = pytest.StashKey()


def is_openrouter_credit_error(text: str) -> bool:
    """Return True when *text* looks like an OpenRouter insufficient-credits failure."""
    return bool(_CREDIT_ERROR_RE.search(text))


def _credits_exhausted(*, client: httpx.Client | None = None) -> bool:
    """Return True when the configured OpenRouter key has no remaining credits.

    Fail-open: missing key, network errors, and non-402 HTTP errors return
    False so the test still runs and reports a real failure.
    """
    api_key = os.environ.get("APP_OPENROUTER_API_KEY")
    if not api_key:
        return False
    return probe_openrouter_key(api_key, client=client).status is OpenRouterStatus.NO_CREDITS


def _session_credits_exhausted(config: pytest.Config) -> bool:
    """Probe OpenRouter once per pytest session and cache the result."""
    if _EXHAUSTED_KEY not in config.stash:
        config.stash[_EXHAUSTED_KEY] = _credits_exhausted()
    return config.stash[_EXHAUSTED_KEY]


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """Xfail marked tests up front when the OpenRouter key is already empty."""
    if item.get_closest_marker("xfail_openrouter_credits") is None:
        return
    if _session_credits_exhausted(item.config):
        pytest.xfail(_XFAIL_REASON)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, Result[pytest.TestReport], None]:
    """Convert a marked test's failure into xfail when it is a credit error."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    if item.get_closest_marker("xfail_openrouter_credits") is None:
        return
    longrepr = "" if report.longrepr is None else str(report.longrepr)
    if not is_openrouter_credit_error(longrepr):
        return
    report.outcome = "skipped"
    report.wasxfail = _XFAIL_REASON
