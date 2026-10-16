"""Tests for the form trigger pass-through activity."""

from typing import Any

import pytest

from syntara.workflows.workflow_engine.activities.form_trigger import form_trigger


class TestFormTriggerPassThrough:
    """Form trigger preserves submitted values and applies output mapping."""

    @pytest.mark.asyncio
    async def test_passes_through_values_without_status_or_metadata(self) -> None:
        values: dict[str, Any] = {"email": "user@example.com", "environment": "stage"}

        result = await form_trigger(values, None)

        assert result == {"output": values}
        assert "status" not in result["output"]
        assert "submitted_by" not in result["output"]

    @pytest.mark.asyncio
    async def test_empty_output_mapping_suppresses_values(self) -> None:
        result = await form_trigger({"email": "user@example.com"}, {})

        assert result == {"output": {}}

    @pytest.mark.asyncio
    async def test_output_mapping_extracts_selected_value(self) -> None:
        result = await form_trigger(
            {"email": "user@example.com", "environment": "stage"},
            {"contact": "${result.email}"},
        )

        assert result == {"output": {"contact": "user@example.com"}}
