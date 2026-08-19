"""Shared fixtures for workflow activity tests."""

from collections.abc import Generator
from unittest.mock import PropertyMock, patch

import pytest

from syntara.core.config.base import Settings
from tests.fixtures.settings import enable_script_nodes


@pytest.fixture(autouse=True)
def _mock_service_identity() -> Generator[None, None, None]:
    """Provide a service_identity for tests running without S2S TLS certificates."""
    with patch.object(Settings, "service_identity", new_callable=PropertyMock, return_value="backend.ao.svc"):
        yield


@pytest.fixture(autouse=True)
def _enable_script_nodes() -> Generator[None, None, None]:
    """Enable script nodes for activity unit tests.

    On platforms without Landlock or unshare (e.g. macOS), also disables
    the sandbox to prevent fail-closed from blocking all script tests.
    """
    from syntara.core.config.base import get_settings
    from syntara.workflows.workflow_engine.activities.script_sandbox import (
        _detect_landlock_abi,
        _detect_unshare_userns,
    )

    with enable_script_nodes():
        settings = get_settings()
        sandbox_available = _detect_landlock_abi() >= 1 or _detect_unshare_userns()
        if not sandbox_available:
            original_sandbox = settings.script_sandbox_enabled
            object.__setattr__(settings, "script_sandbox_enabled", False)
            try:
                yield
            finally:
                object.__setattr__(settings, "script_sandbox_enabled", original_sandbox)
        else:
            yield
