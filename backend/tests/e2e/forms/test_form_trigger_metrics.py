"""E2E coverage for Form Trigger submission latency metrics."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from prometheus_client.parser import text_string_to_metric_families

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.client import AuthenticatedClient
    from syntara_api_client.models import WorkflowCreate, WorkflowRead

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from ._helpers import (
    assert_consumer_completed,
    create_form_trigger_workflow,
    submit_form_trigger_and_track,
)
from ._workflows import REQUIRED_AND_OPTIONAL_FIELDS

pytestmark = [pytest.mark.e2e]

_METRICS_URL = f"{os.environ['APP_BASE_URL'].rstrip('/')}/metrics"
_HISTOGRAM_NAME = "orchestrator_form_trigger_submission_start_seconds"
_METRIC_LABELS = {"component": "execution_service"}
_VALID_SUBMISSION: dict[str, Any] = {
    "required_text": "FORM_TRIGGER_METRIC_CONTROL_97126",
    "required_email": "metric-control@example.com",
    "optional_number": 7,
}


def _histogram_sample(
    client: httpx.Client,
    sample_suffix: str,
) -> float:
    """Read a Form Trigger histogram sample from the configured E2E client scrape."""
    response = client.get(_METRICS_URL)
    assert response.status_code == HTTPStatus.OK, f"OpenMetrics scrape returned {response.status_code}: {response.text}"

    sample_name = f"{_HISTOGRAM_NAME}_{sample_suffix}"
    for family in text_string_to_metric_families(response.text):
        if family.name != _HISTOGRAM_NAME:
            continue
        for sample in family.samples:
            if sample.name == sample_name and sample.labels == _METRIC_LABELS:
                return float(sample.value)
    return 0.0


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
    syntara_client: AuthenticatedClient,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """A successful Form Trigger submission adds one latency record.

    Procedure:
    1. Create a workflow and snapshot the current metric count.
    2. Submit valid form data and wait for the consumer to complete.
    3. Check that at least one valid histogram observation was added.

    Expected:
    - The histogram count increases and its latency sum increases by a positive amount in seconds.
    """
    workflow = _create_workflow(workflow_factory, first_project_id, name_prefix="e2e-form-trigger-metric")
    client = syntara_client.get_httpx_client()
    before_count = _histogram_sample(client, "count")
    before_sum = _histogram_sample(client, "sum")

    execution = submit_form_trigger_and_track(
        syntara_api,
        workflow,
        _VALID_SUBMISSION,
        form_execution_cleanup,
    )
    assert_consumer_completed(syntara_api, UUID(str(execution.id)))

    after_count = _histogram_sample(client, "count")
    after_sum = _histogram_sample(client, "sum")
    assert after_count >= before_count + 1
    sum_delta_seconds = after_sum - before_sum
    assert sum_delta_seconds > 0
