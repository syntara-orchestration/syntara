"""Shared fixtures for telemetry performance tests."""

from collections.abc import Generator

import pytest

from tests.fixtures.settings import enable_script_nodes


@pytest.fixture(autouse=True)
def _enable_script_nodes() -> Generator[None, None, None]:
    """Enable script nodes for telemetry overhead tests that call execute_script_activity directly."""
    with enable_script_nodes():
        yield
