"""Test that script activity checks runtime setting before executing."""

from unittest.mock import AsyncMock, patch

import pytest
from temporalio.exceptions import ApplicationError


class TestScriptActivitySettingCheck:
    """Test runtime setting enforcement in script activity."""

    @pytest.mark.asyncio
    async def test_script_nodes_disabled_raises_application_error(self) -> None:
        from syntara.workflows.workflow_engine.activities.script_activity import (
            execute_script_activity,
        )

        config = {"language": "bash", "code": "echo hello"}

        with patch(
            "syntara.workflows.workflow_engine.activities.script_activity.get_runtime_settings"
        ) as mock_settings:
            cache = AsyncMock()
            cache.get_bool.return_value = False
            mock_settings.return_value = cache

            with patch("syntara.workflows.workflow_engine.activities.script_activity.activity"):
                with pytest.raises(ApplicationError, match="Script nodes are disabled"):
                    await execute_script_activity(config, output_config=None)
