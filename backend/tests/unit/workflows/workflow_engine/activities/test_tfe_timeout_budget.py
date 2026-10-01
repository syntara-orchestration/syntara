"""TFE activity timeout budget must keep the HTTP client under Temporal."""

from typing import Any

from syntara.workflows.workflow_engine.activities.tfe_common import (
    build_client_from_resolution,
    engine_timeout_from_input,
)
from syntara.workflows.workflow_engine.constants import ENGINE_TIMEOUT_SECONDS_KEY


def test_engine_timeout_from_input_reads_injected_budget() -> None:
    assert engine_timeout_from_input({ENGINE_TIMEOUT_SECONDS_KEY: 180}) == 180
    assert engine_timeout_from_input({}) is None
    assert engine_timeout_from_input({ENGINE_TIMEOUT_SECONDS_KEY: "180"}) is None


def test_build_client_caps_http_timeout_under_engine_budget() -> None:
    integration: dict[str, Any] = {
        "base_url": "https://app.terraform.io",
        "organization": "acme",
        "verify_ssl": True,
    }
    client = build_client_from_resolution(
        integration,
        "token",
        engine_timeout_seconds=180,
    )
    assert client._timeout == 170.0
    assert client._request_timeout(mutating=True) == 170.0
    assert client._request_timeout(mutating=False) < 170.0
