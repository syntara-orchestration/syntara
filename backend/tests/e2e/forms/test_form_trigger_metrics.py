"""E2E coverage for Form Trigger submission latency metrics."""

from __future__ import annotations

import json
import os
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import pytest
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context
from syntara_api_client.models import SettingUpdate, WorkflowCreate

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models import WorkflowRead

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from ._helpers import (
    assert_and_get_response,
    assert_consumer_completed,
    create_form_trigger_workflow,
    submit_form_trigger_and_track,
)
from ._workflows import REQUIRED_AND_OPTIONAL_FIELDS

pytestmark = [pytest.mark.e2e]

_METRIC_TYPE = "form_trigger_submission_start_ms"
_METRIC_LABELS = {"component": "execution_service"}
_VALID_SUBMISSION: dict[str, Any] = {
    "required_text": "FORM_TRIGGER_METRIC_CONTROL_97126",
    "required_email": "metric-control@example.com",
    "optional_number": 7,
}


@pytest.fixture(scope="module", autouse=True)
def metrics_perf_test_mode(
    syntara_api: SyntaraApiRegistry,
    syntara_base_url: str,
) -> Generator[None, None, None]:
    """Enable the metrics store for this module and restore its prior effective value."""
    setting = assert_and_get_response(syntara_api.settings.get(key="metrics.perf_test_mode"))
    original_value = setting.value if setting.value is not None else setting.default_value
    assert isinstance(original_value, bool)
    syntara_api.settings.update(
        key="metrics.perf_test_mode",
        body=SettingUpdate(value=True),
    ).assert_and_get()
    try:
        yield
    finally:
        # PATCH cannot restore null; restoring the effective default is behaviorally equivalent.
        syntara_api.settings.update(
            key="metrics.perf_test_mode",
            body=SettingUpdate(value=original_value),
        ).assert_and_get()
        # _guard synchronizes the recorder flag and flushes the store on this request.
        response = httpx.get(
            f"{syntara_base_url.rstrip('/')}/_internal/metrics/summary",
            timeout=10,
            verify=e2e_ssl_context(),
        )
        expected_status = HTTPStatus.OK if original_value else HTTPStatus.NOT_FOUND
        assert response.status_code == expected_status, (
            f"Expected metrics summary status {expected_status}, got {response.status_code}: {response.text}"
        )


def _metric_page(syntara_base_url: str) -> tuple[list[dict[str, Any]], int]:
    """Read the filtered Form Trigger latency records from the internal metrics API."""
    response = httpx.get(
        f"{syntara_base_url.rstrip('/')}/_internal/metrics/records",
        params={
            "metric_type": _METRIC_TYPE,
            "labels": json.dumps(_METRIC_LABELS),
            "limit": 10000,
        },
        timeout=10,
        verify=e2e_ssl_context(),
    )
    assert response.status_code == 200, f"Metrics API returned {response.status_code}: {response.text}"
    payload = response.json()
    assert isinstance(payload, dict), f"Expected metrics page object, got {payload!r}"
    records = payload.get("records")
    total = payload.get("total")
    assert isinstance(records, list), f"Expected metrics records list, got {records!r}"
    assert isinstance(total, int), f"Expected integer metrics total, got {total!r}"
    assert all(isinstance(record, dict) for record in records), f"Expected metric objects, got {records!r}"
    return records, total


def _wait_for_metric_count(syntara_base_url: str, expected_minimum: int) -> tuple[list[dict[str, Any]], int]:
    """Poll the metrics store until it contains at least the expected number of records."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        records, total = _metric_page(syntara_base_url)
        if total >= expected_minimum:
            return records, total
        time.sleep(0.25)
    pytest.fail(f"Metrics store did not reach {expected_minimum} records within 15 seconds")


def _create_workflow(
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    *,
    name_prefix: str,
) -> WorkflowRead:
    """Create a Form Trigger workflow for a metric test."""
    return create_form_trigger_workflow(
        workflow_factory,
        first_project_id,
        name_prefix=name_prefix,
        description="E2E: Form Trigger submission metric",
        form_fields=REQUIRED_AND_OPTIONAL_FIELDS,
    )


def test_form_trigger_submission_records_latency_metric(
    syntara_api: SyntaraApiRegistry,
    syntara_base_url: str,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """A successful Form Trigger submission adds one latency record.

    Procedure:
    1. Create a workflow and snapshot the current metric count.
    2. Submit valid form data and wait for the consumer to complete.
    3. Check that exactly one valid latency record was added.

    Expected:
    - The metric count increases by one and the new record is in milliseconds.
    """
    workflow = _create_workflow(workflow_factory, first_project_id, name_prefix="e2e-form-trigger-metric")
    _, before = _metric_page(syntara_base_url)

    execution = submit_form_trigger_and_track(
        syntara_api,
        workflow,
        _VALID_SUBMISSION,
        form_execution_cleanup,
    )
    assert_consumer_completed(syntara_api, UUID(str(execution.id)))

    records, total = _wait_for_metric_count(syntara_base_url, before + 1)
    assert total == before + 1
    record = records[-1]
    assert record["metric_type"] == _METRIC_TYPE
    assert record["labels"] == _METRIC_LABELS
    assert record["unit"] == "ms"
    assert record["value"] >= 0
