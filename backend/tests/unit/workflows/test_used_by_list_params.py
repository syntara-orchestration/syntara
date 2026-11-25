"""Unit tests for WorkflowUsedByListParams validation.

Covers Helen's non-blocking hardening on PR #1318: ``trigger_node_ids`` is capped so an unbounded
client-supplied list cannot blow up the OR'd JSONB containment scan on the Used-By endpoint.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from syntara.workflows.models.query_params import WorkflowUsedByListParams

_CAP = 50


def test_trigger_node_ids_defaults_to_none() -> None:
    assert WorkflowUsedByListParams().trigger_node_ids is None


def test_trigger_node_ids_accepts_up_to_the_cap() -> None:
    params = WorkflowUsedByListParams(trigger_node_ids=[f"trigger_{i}" for i in range(_CAP)])
    assert params.trigger_node_ids is not None
    assert len(params.trigger_node_ids) == _CAP


def test_trigger_node_ids_rejects_over_the_cap() -> None:
    with pytest.raises(ValidationError):
        WorkflowUsedByListParams(trigger_node_ids=[f"trigger_{i}" for i in range(_CAP + 1)])
