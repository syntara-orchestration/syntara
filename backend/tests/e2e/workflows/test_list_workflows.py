"""E2E tests for workflow list endpoint."""

import pytest
from syntara_api_client.api import SyntaraApiRegistry

pytestmark = [pytest.mark.e2e]


class TestWorkflows:
    """E2E tests for workflow GET endpoints."""

    def test_list_workflows(self, syntara_api: SyntaraApiRegistry) -> None:
        workflows = syntara_api.workflows.list().assert_and_get()
        assert isinstance(workflows.resources, list)
