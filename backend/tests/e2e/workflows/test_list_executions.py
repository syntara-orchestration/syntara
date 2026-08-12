"""E2E tests for execution list endpoint."""

import pytest
from syntara_api_client.api import SyntaraApiRegistry

pytestmark = [pytest.mark.e2e]


class TestExecutions:
    """E2E tests for execution GET endpoints."""

    def test_list_executions(self, syntara_api: SyntaraApiRegistry) -> None:
        executions = syntara_api.executions.list().assert_and_get()
        assert isinstance(executions.resources, list)
