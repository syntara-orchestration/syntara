"""Integration tests for schedule reconciliation DB query.

Validates that the jsonb_path_exists query uses the correct ::jsonpath
cast so asyncpg does not bind the argument as VARCHAR (which PostgreSQL
rejects with ``function jsonb_path_exists(jsonb, character varying)
does not exist``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, literal_column
from sqlmodel import select

from nexus.workflows.models import Workflow, WorkflowVersion

if TYPE_CHECKING:
    from tests.integration.helpers.workflow import WorkflowFactory


_SCHEDULED_DEFINITION: dict[str, object] = {
    "schema_version": "2.0.0",
    "name": "scheduled-wf",
    "triggers": [
        {
            "id": "trigger_sched",
            "type": "scheduled_trigger",
            "parameters": {"schedule_type": "cron", "cron": "0 9 * * *"},
        }
    ],
    "nodes": [
        {
            "id": "script_node",
            "name": "Script",
            "type": "script",
            "parameters": {"language": "python", "code": "pass"},
        }
    ],
    "edges": [{"from": "trigger_sched", "to": "script_node"}],
}


@pytest.mark.asyncio
async def test_jsonb_path_exists_scheduled_trigger_filter(
    workflow_factory: WorkflowFactory,
) -> None:
    """jsonb_path_exists with ::jsonpath cast finds scheduled-trigger workflows.

    Reproduces the bug where a bare string argument was bound as VARCHAR by
    asyncpg, causing ``function jsonb_path_exists(jsonb, character varying)
    does not exist``.
    """
    scheduled_wf, scheduled_ver = await workflow_factory.create("scheduled-wf")
    scheduled_ver.workflow_definition = _SCHEDULED_DEFINITION
    await workflow_factory.session.flush()

    await workflow_factory.create("manual-wf")
    await workflow_factory.session.commit()

    triggers_col = WorkflowVersion.workflow_definition["triggers"]
    result = await workflow_factory.session.exec(
        select(Workflow.id, triggers_col)
        .join(WorkflowVersion, WorkflowVersion.id == Workflow.published_version_id)  # type: ignore[arg-type]
        .where(
            Workflow.published_version_id.is_not(None),  # type: ignore[union-attr]
            Workflow.deleted_at.is_(None),  # type: ignore[union-attr]
            func.jsonb_path_exists(
                WorkflowVersion.workflow_definition,
                literal_column("'$.triggers[*] ? (@.type == \"scheduled_trigger\")'::jsonpath"),
            ),
        )
    )
    rows = result.all()

    returned_ids = {row[0] for row in rows}
    assert scheduled_wf.id in returned_ids
    assert len(returned_ids) == 1

    triggers = rows[0][1]
    assert any(t["type"] == "scheduled_trigger" for t in triggers)
