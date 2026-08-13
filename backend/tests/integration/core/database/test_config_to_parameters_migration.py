"""Integration tests for the config→parameters JSONB migration.

Tests the SQL logic from migration 433e243396da which renames the "config"
key to "parameters" in workflow_definition JSONB stored in workflow_versions,
covering both the "nodes" and "triggers" arrays.
"""

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from syntara.core.models import User

# The exact SQL from the alembic migration upgrade() - nodes
_UPGRADE_NODES_SQL = """
    UPDATE workflow_versions
    SET workflow_definition = jsonb_set(
        workflow_definition,
        '{nodes}',
        (
            SELECT jsonb_agg(
                CASE
                    WHEN node ? 'config' AND NOT (node ? 'parameters')
                    THEN (node || jsonb_build_object('parameters', node -> 'config')) - 'config'
                    ELSE node
                END
            )
            FROM jsonb_array_elements(workflow_definition -> 'nodes') AS node
        )
    )
    WHERE workflow_definition ? 'nodes'
    AND EXISTS (
        SELECT 1
        FROM jsonb_array_elements(workflow_definition -> 'nodes') AS node
        WHERE node ? 'config'
    )
"""

# The exact SQL from the alembic migration upgrade() - triggers
_UPGRADE_TRIGGERS_SQL = """
    UPDATE workflow_versions
    SET workflow_definition = jsonb_set(
        workflow_definition,
        '{triggers}',
        (
            SELECT jsonb_agg(
                CASE
                    WHEN trigger_node ? 'config' AND NOT (trigger_node ? 'parameters')
                    THEN (trigger_node || jsonb_build_object('parameters', trigger_node -> 'config')) - 'config'
                    ELSE trigger_node
                END
            )
            FROM jsonb_array_elements(workflow_definition -> 'triggers') AS trigger_node
        )
    )
    WHERE workflow_definition ? 'triggers'
    AND EXISTS (
        SELECT 1
        FROM jsonb_array_elements(workflow_definition -> 'triggers') AS trigger_node
        WHERE trigger_node ? 'config'
    )
"""

# The exact SQL from the alembic migration downgrade() - nodes
_DOWNGRADE_NODES_SQL = """
    UPDATE workflow_versions
    SET workflow_definition = jsonb_set(
        workflow_definition,
        '{nodes}',
        (
            SELECT jsonb_agg(
                CASE
                    WHEN node ? 'parameters' AND NOT (node ? 'config')
                    THEN (node || jsonb_build_object('config', node -> 'parameters')) - 'parameters'
                    ELSE node
                END
            )
            FROM jsonb_array_elements(workflow_definition -> 'nodes') AS node
        )
    )
    WHERE workflow_definition ? 'nodes'
    AND EXISTS (
        SELECT 1
        FROM jsonb_array_elements(workflow_definition -> 'nodes') AS node
        WHERE node ? 'parameters'
    )
"""

# The exact SQL from the alembic migration downgrade() - triggers
_DOWNGRADE_TRIGGERS_SQL = """
    UPDATE workflow_versions
    SET workflow_definition = jsonb_set(
        workflow_definition,
        '{triggers}',
        (
            SELECT jsonb_agg(
                CASE
                    WHEN trigger_node ? 'parameters' AND NOT (trigger_node ? 'config')
                    THEN (trigger_node || jsonb_build_object('config', trigger_node -> 'parameters')) - 'parameters'
                    ELSE trigger_node
                END
            )
            FROM jsonb_array_elements(workflow_definition -> 'triggers') AS trigger_node
        )
    )
    WHERE workflow_definition ? 'triggers'
    AND EXISTS (
        SELECT 1
        FROM jsonb_array_elements(workflow_definition -> 'triggers') AS trigger_node
        WHERE trigger_node ? 'parameters'
    )
"""


def _make_workflow_def(
    nodes: list[dict[str, Any]],
    triggers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if triggers is None:
        triggers = [{"id": "t", "type": "manual_trigger", "parameters": {}}]
    return {
        "schema_version": "2.0.0",
        "name": "migration-test",
        "triggers": triggers,
        "nodes": nodes,
        "edges": [{"from": triggers[0]["id"], "to": nodes[0]["id"]}] if nodes and triggers else [],
    }


async def _insert_version(
    session: AsyncSession,
    workflow_def: dict[str, Any],
    user_id: str,
    project_id: str,
) -> str:
    """Insert a workflow + workflow_version row and return the version ID."""
    wf_id = str(uuid4())
    ver_id = str(uuid4())
    # Insert workflow first (is_enabled=false, no published_version_id yet)
    await session.exec(  # type: ignore[call-overload]
        text("""
            INSERT INTO workflows
                (id, name, current_version, is_enabled,
                 created_by, updated_by, labels, project_id)
            VALUES (:wf_id, :name, 1, false, :user_id, :user_id, :empty_json, :project_id)
        """),
        params={
            "wf_id": wf_id,
            "name": f"mig-test-{wf_id[:8]}",
            "user_id": user_id,
            "empty_json": "{}",
            "project_id": project_id,
        },
    )
    # Insert version (FK to workflow now exists)
    await session.exec(  # type: ignore[call-overload]
        text("""
            INSERT INTO workflow_versions
                (id, workflow_id, version, schema_version, workflow_definition,
                 created_by, updated_by, labels)
            VALUES
                (:ver_id, :wf_id, 1, '2.0.0', CAST(:wd AS jsonb),
                 :user_id, :user_id, :empty_json)
        """),
        params={
            "ver_id": ver_id,
            "wf_id": wf_id,
            "wd": json.dumps(workflow_def),
            "user_id": user_id,
            "empty_json": "{}",
        },
    )
    # Set published_version_id + is_enabled now that version exists
    await session.exec(  # type: ignore[call-overload]
        text("""
            UPDATE workflows SET published_version_id = :ver_id, is_enabled = true
            WHERE id = :wf_id
        """),
        params={"ver_id": ver_id, "wf_id": wf_id},
    )
    await session.flush()
    return ver_id


async def _get_nodes(session: AsyncSession, ver_id: str) -> list[dict[str, Any]]:
    """Read the nodes array from a workflow_version row."""
    result = await session.exec(  # type: ignore[call-overload]
        text("SELECT workflow_definition -> 'nodes' FROM workflow_versions WHERE id = :id"),
        params={"id": ver_id},
    )
    row: Any = result.one()[0]
    nodes: list[dict[str, Any]] = json.loads(row) if isinstance(row, str) else row
    return nodes


async def _get_triggers(session: AsyncSession, ver_id: str) -> list[dict[str, Any]]:
    """Read the triggers array from a workflow_version row."""
    result = await session.exec(  # type: ignore[call-overload]
        text("SELECT workflow_definition -> 'triggers' FROM workflow_versions WHERE id = :id"),
        params={"id": ver_id},
    )
    row: Any = result.one()[0]
    triggers: list[dict[str, Any]] = json.loads(row) if isinstance(row, str) else row
    return triggers


async def _run_upgrade(session: AsyncSession) -> None:
    await session.exec(text(_UPGRADE_NODES_SQL))  # type: ignore[call-overload]
    await session.exec(text(_UPGRADE_TRIGGERS_SQL))  # type: ignore[call-overload]


async def _run_downgrade(session: AsyncSession) -> None:
    await session.exec(text(_DOWNGRADE_NODES_SQL))  # type: ignore[call-overload]
    await session.exec(text(_DOWNGRADE_TRIGGERS_SQL))  # type: ignore[call-overload]


@pytest.mark.integration
@pytest.mark.asyncio
class TestConfigToParametersMigrationNodes:
    """Tests for the config→parameters JSONB rename SQL on nodes."""

    async def test_basic_rename(self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID) -> None:
        """Single node with "config" is renamed to "parameters"."""
        wd = _make_workflow_def(
            [
                {"id": "n1", "type": "script", "config": {"language": "python", "code": "print(1)"}},
            ]
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)

        nodes = await _get_nodes(test_db_session, ver_id)
        assert "parameters" in nodes[0]
        assert "config" not in nodes[0]
        assert nodes[0]["parameters"] == {"language": "python", "code": "print(1)"}

    async def test_multiple_nodes(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """All nodes with "config" are renamed."""
        wd = _make_workflow_def(
            [
                {"id": "n1", "type": "script", "config": {"language": "bash", "code": "echo a"}},
                {"id": "n2", "type": "http_request", "config": {"method": "GET", "url": "http://x"}},
                {"id": "n3", "type": "condition", "config": {"condition": "1 == 1"}},
            ]
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)

        nodes = await _get_nodes(test_db_session, ver_id)
        for node in nodes:
            assert "parameters" in node, f"node {node['id']} missing 'parameters'"
            assert "config" not in node, f"node {node['id']} still has 'config'"

    async def test_already_migrated_unchanged(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Node already using "parameters" is left unchanged."""
        wd = _make_workflow_def(
            [
                {"id": "n1", "type": "script", "parameters": {"language": "python", "code": "x"}},
            ]
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)

        nodes = await _get_nodes(test_db_session, ver_id)
        assert "parameters" in nodes[0]
        assert "config" not in nodes[0]
        assert nodes[0]["parameters"] == {"language": "python", "code": "x"}

    async def test_mixed_nodes(self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID) -> None:
        """Only nodes with "config" are renamed; "parameters" nodes stay."""
        wd = _make_workflow_def(
            [
                {"id": "old", "type": "script", "config": {"language": "bash", "code": "echo old"}},
                {"id": "new", "type": "script", "parameters": {"language": "bash", "code": "echo new"}},
            ]
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)

        nodes = await _get_nodes(test_db_session, ver_id)
        by_id = {n["id"]: n for n in nodes}
        assert "parameters" in by_id["old"]
        assert "config" not in by_id["old"]
        assert by_id["old"]["parameters"] == {"language": "bash", "code": "echo old"}
        assert by_id["new"]["parameters"] == {"language": "bash", "code": "echo new"}

    async def test_no_nodes_key_untouched(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Row without "nodes" in workflow_definition is not modified."""
        wd: dict[str, Any] = {"schema_version": "1.0.0", "metadata": {"name": "legacy"}}
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)

        result = await test_db_session.exec(  # type: ignore[call-overload]
            text("SELECT workflow_definition FROM workflow_versions WHERE id = :id"),
            params={"id": ver_id},
        )
        row = result.one()[0]
        stored = json.loads(row) if isinstance(row, str) else row
        assert "nodes" not in stored

    async def test_downgrade_reverts(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Downgrade renames "parameters" back to "config"."""
        wd = _make_workflow_def(
            [
                {"id": "n1", "type": "script", "parameters": {"language": "python", "code": "x"}},
            ]
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_downgrade(test_db_session)

        nodes = await _get_nodes(test_db_session, ver_id)
        assert "config" in nodes[0]
        assert "parameters" not in nodes[0]
        assert nodes[0]["config"] == {"language": "python", "code": "x"}

    async def test_upgrade_then_downgrade_roundtrip(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Upgrade followed by downgrade restores original data."""
        original_config = {"language": "bash", "code": "echo roundtrip"}
        wd = _make_workflow_def(
            [
                {"id": "n1", "type": "script", "config": original_config},
            ]
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)
        nodes = await _get_nodes(test_db_session, ver_id)
        assert "parameters" in nodes[0]

        await _run_downgrade(test_db_session)
        nodes = await _get_nodes(test_db_session, ver_id)
        assert "config" in nodes[0]
        assert nodes[0]["config"] == original_config


@pytest.mark.integration
@pytest.mark.asyncio
class TestConfigToParametersMigrationTriggers:
    """Tests for the config→parameters JSONB rename SQL on triggers."""

    async def test_trigger_config_renamed(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Trigger with "config" is renamed to "parameters"."""
        wd = _make_workflow_def(
            nodes=[{"id": "n1", "type": "script", "parameters": {}}],
            triggers=[{"id": "t1", "type": "webhook", "config": {"secret": "abc"}}],
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)

        triggers = await _get_triggers(test_db_session, ver_id)
        assert "parameters" in triggers[0]
        assert "config" not in triggers[0]
        assert triggers[0]["parameters"] == {"secret": "abc"}

    async def test_trigger_already_migrated(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Trigger already using "parameters" is left unchanged."""
        wd = _make_workflow_def(
            nodes=[{"id": "n1", "type": "script", "parameters": {}}],
            triggers=[{"id": "t1", "type": "manual_trigger", "parameters": {"key": "val"}}],
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)

        triggers = await _get_triggers(test_db_session, ver_id)
        assert "parameters" in triggers[0]
        assert "config" not in triggers[0]
        assert triggers[0]["parameters"] == {"key": "val"}

    async def test_mixed_triggers(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Multiple triggers: only those with "config" are renamed."""
        wd = _make_workflow_def(
            nodes=[{"id": "n1", "type": "script", "parameters": {}}],
            triggers=[
                {"id": "t1", "type": "webhook", "config": {"secret": "old"}},
                {"id": "t2", "type": "manual_trigger", "parameters": {"key": "new"}},
            ],
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)

        triggers = await _get_triggers(test_db_session, ver_id)
        by_id = {t["id"]: t for t in triggers}
        assert "parameters" in by_id["t1"]
        assert "config" not in by_id["t1"]
        assert by_id["t1"]["parameters"] == {"secret": "old"}
        assert by_id["t2"]["parameters"] == {"key": "new"}

    async def test_trigger_downgrade_reverts(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Downgrade renames trigger "parameters" back to "config"."""
        wd = _make_workflow_def(
            nodes=[{"id": "n1", "type": "script", "parameters": {}}],
            triggers=[{"id": "t1", "type": "webhook", "parameters": {"secret": "abc"}}],
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_downgrade(test_db_session)

        triggers = await _get_triggers(test_db_session, ver_id)
        assert "config" in triggers[0]
        assert "parameters" not in triggers[0]
        assert triggers[0]["config"] == {"secret": "abc"}

    async def test_nodes_and_triggers_both_migrated(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Both nodes and triggers with "config" are renamed in the same row."""
        wd = _make_workflow_def(
            nodes=[{"id": "n1", "type": "script", "config": {"code": "x"}}],
            triggers=[{"id": "t1", "type": "webhook", "config": {"secret": "s"}}],
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)

        nodes = await _get_nodes(test_db_session, ver_id)
        assert "parameters" in nodes[0]
        assert "config" not in nodes[0]

        triggers = await _get_triggers(test_db_session, ver_id)
        assert "parameters" in triggers[0]
        assert "config" not in triggers[0]

    async def test_full_roundtrip_nodes_and_triggers(
        self, test_db_session: AsyncSession, test_user: "User", test_project_id: UUID
    ) -> None:
        """Upgrade then downgrade restores both nodes and triggers."""
        wd = _make_workflow_def(
            nodes=[{"id": "n1", "type": "script", "config": {"code": "x"}}],
            triggers=[{"id": "t1", "type": "webhook", "config": {"secret": "s"}}],
        )
        ver_id = await _insert_version(test_db_session, wd, str(test_user.id), str(test_project_id))

        await _run_upgrade(test_db_session)
        nodes = await _get_nodes(test_db_session, ver_id)
        triggers = await _get_triggers(test_db_session, ver_id)
        assert "parameters" in nodes[0]
        assert "parameters" in triggers[0]

        await _run_downgrade(test_db_session)
        nodes = await _get_nodes(test_db_session, ver_id)
        triggers = await _get_triggers(test_db_session, ver_id)
        assert "config" in nodes[0]
        assert nodes[0]["config"] == {"code": "x"}
        assert "config" in triggers[0]
        assert triggers[0]["config"] == {"secret": "s"}
