"""Component-only filtering tests do not require database seeding."""

import pytest


@pytest.fixture(autouse=True)
def _seed_authenticated_group() -> None:
    """Override the parent DB seed, matching existing component integration tests."""
