"""Shared fixtures for integration unit tests."""

from collections.abc import Generator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _skip_ssrf_validation(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Bypass write-time SSRF base_url validation for tests using placeholder hostnames.

    Integration configs in tests use non-resolvable hosts (e.g. gateway.example.com), so the
    DNS-resolving SSRF check at the create/patch boundary would reject them. Tests that
    exercise the SSRF check itself opt out with ``@pytest.mark.ssrf_enforced``.
    """
    if request.node.get_closest_marker("ssrf_enforced"):
        yield
        return
    with patch(
        "syntara.integrations.services.integration_service.validate_url_no_ssrf",
        return_value=None,
    ):
        yield
