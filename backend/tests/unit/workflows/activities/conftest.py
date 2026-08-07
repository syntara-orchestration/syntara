"""Shared fixtures for workflow activity tests."""

from collections.abc import Generator
from unittest.mock import PropertyMock, patch

import pytest

from nexus.core.config.base import Settings


@pytest.fixture(autouse=True)
def _mock_service_identity() -> Generator[None, None, None]:
    """Provide a service_identity for tests running without S2S TLS certificates."""
    with patch.object(Settings, "service_identity", new_callable=PropertyMock, return_value="backend.ao.svc"):
        yield


@pytest.fixture(autouse=True)
def _enable_script_nodes() -> Generator[None, None, None]:
    """Enable script nodes for activity unit tests."""
    with patch.object(Settings, "script_nodes_enabled", new_callable=PropertyMock, return_value=True):
        yield
