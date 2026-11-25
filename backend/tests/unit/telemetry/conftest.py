"""Shared fixtures for telemetry unit tests."""

import pytest

# Common test data constants
VALID_WORKFLOW_EXECUTION_ID = "550e8400-e29b-41d4-a716-446655440000"
VALID_WORKFLOW_ID = "b8edd493-98c0-44e8-babb-34eb9256aa50"
VALID_NODE_HASH = "b" * 64
SAMPLE_NODE_DEF = {"name": "test-node", "type": "script_python"}


@pytest.fixture
def valid_workflow_execution_id() -> str:
    """Return a valid workflow execution ID for telemetry tests."""
    return VALID_WORKFLOW_EXECUTION_ID


@pytest.fixture
def valid_node_hash() -> str:
    """Return a valid node hash for telemetry tests."""
    return VALID_NODE_HASH


@pytest.fixture
def sample_node_def() -> dict[str, str]:
    """Return a sample node definition for telemetry tests."""
    return SAMPLE_NODE_DEF.copy()
