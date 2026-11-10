"""Runtime settings for service tests that do not start the API lifespan."""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _runtime_settings(override_runtime_settings) -> Generator[None, None, None]:
    with override_runtime_settings({}):
        yield
