"""Shared fixtures for telemetry unit tests."""

from collections.abc import Generator

import pytest

from syntara.telemetry.events.base import _get_container_image_version

# Common test data constants
VALID_WORKFLOW_EXECUTION_ID = "550e8400-e29b-41d4-a716-446655440000"
VALID_WORKFLOW_ID = "b8edd493-98c0-44e8-babb-34eb9256aa50"
VALID_NODE_HASH = "b" * 64
SAMPLE_NODE_DEF = {"name": "test-node", "type": "script"}


@pytest.fixture(autouse=True)
def _isolate_container_image_version_cache() -> Generator[None, None, None]:
    """Keep image-version overrides from leaking between telemetry tests."""
    from syntara.telemetry.events.base import _get_container_image_version

    _get_container_image_version.cache_clear()
    yield
    _get_container_image_version.cache_clear()


@pytest.fixture
def telemetry_image_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set an explicit image version for complete event-property assertions."""
    from syntara.core.config.base import get_settings
    from syntara.telemetry.events.base import _get_container_image_version

    monkeypatch.setattr(get_settings(), "container_image_version", "img-tag")
    _get_container_image_version.cache_clear()


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


@pytest.fixture(autouse=True)
def isolate_container_image_version_cache() -> Generator[None, None, None]:
    """Keep a process-lifetime production cache from coupling independent tests."""
    _get_container_image_version.cache_clear()
    yield
    _get_container_image_version.cache_clear()
