"""Integration tests for the node-kind registry and kill switch (ANSTRAT-1750).

Exercises the full round trip: flip a kind off through the API, observe that
``POST /workflows/validate`` refuses definitions using it and that
``GET /node_kinds`` reports it as disabled, then flip it back on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
import sqlalchemy

from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.workflows.node_kind_switch import DISABLED_NODE_KINDS_SETTING_KEY

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncEngine

_NODE_KINDS_URL = "/api/v1/node_kinds"
_VALIDATE_URL = "/api/v1/workflows/validate"


def _definition_with_script() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "kill-switch-target",
        "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "print(1)"}}],
        "edges": [{"from": "t1", "to": "n1"}],
    }


@pytest_asyncio.fixture(autouse=True)
async def _reset_kill_switch(test_db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Clear the setting and the process-wide settings cache around each test.

    The settings cache is a singleton shared by every test in the worker, so a
    leftover disabled kind would leak into unrelated tests.
    """
    yield
    async with test_db_engine.begin() as conn:
        await conn.execute(
            sqlalchemy.text("UPDATE runtime_settings SET value = NULL WHERE key = :key"),
            {"key": DISABLED_NODE_KINDS_SETTING_KEY},
        )
    await get_runtime_settings().invalidate(DISABLED_NODE_KINDS_SETTING_KEY)


def _by_kind(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["kind"]: entry for entry in payload["resources"]}


class TestListNodeKinds:
    """GET /node_kinds is readable by any authenticated principal."""

    @pytest.mark.asyncio
    async def test_lists_registry_with_caller_verdicts(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.get(_NODE_KINDS_URL)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["disabled_kinds"] == []
        entries = _by_kind(payload)
        assert entries["script"] == {
            "kind": "script",
            "category": "action",
            "enabled": True,
            "switchable": True,
            "deniable_actions": ["execute", "write"],
            "can_write": True,
            "attributes": [{"name": "language", "allowed_values": ["bash", "python"]}],
        }
        assert entries["condition"]["switchable"] is False
        assert entries["condition"]["deniable_actions"] == []


class TestSetNodeKindEnabledErrors:
    """Unknown and non-switchable kinds are rejected."""

    @pytest.mark.asyncio
    async def test_unknown_kind_returns_404(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.put(f"{_NODE_KINDS_URL}/not_a_kind/enabled", json={"enabled": False})
        assert resp.status_code == 404
        assert resp.json()["code"] == "NODE_KIND_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_flow_control_kind_returns_422(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.put(f"{_NODE_KINDS_URL}/condition/enabled", json={"enabled": False})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "NODE_KIND_NOT_SWITCHABLE"
        assert "flow control" in body["detail"]


class TestKillSwitchRoundTrip:
    """Flipping a kind off blocks validation, flipping it back on restores it."""

    @pytest.mark.asyncio
    async def test_disable_then_enable(self, auth_client: AsyncClient) -> None:
        # The definition validates cleanly while the kind is enabled.
        resp = await auth_client.post(_VALIDATE_URL, json={"workflow_definition": _definition_with_script()})
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is True

        # Disable the kind.
        resp = await auth_client.put(f"{_NODE_KINDS_URL}/script/enabled", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json() == {
            "kind": "script",
            "category": "action",
            "enabled": False,
            "switchable": True,
            "deniable_actions": ["execute", "write"],
            "can_write": True,
            "attributes": [{"name": "language", "allowed_values": ["bash", "python"]}],
        }

        # The registry listing reflects the switch.
        resp = await auth_client.get(_NODE_KINDS_URL)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["disabled_kinds"] == ["script"]
        assert _by_kind(payload)["script"]["enabled"] is False

        # Validation now reports the finding and rejects the definition.
        resp = await auth_client.post(_VALIDATE_URL, json={"workflow_definition": _definition_with_script()})
        assert resp.status_code == 422
        result = resp.json()["validation_result"]
        assert result["is_valid"] is False
        findings = [f for f in result["findings"] if f["category"] == "node_kind_disabled"]
        assert len(findings) == 1
        assert findings[0]["severity"] == "error"
        assert findings[0]["node_id"] == "n1"
        assert "script" in findings[0]["message"]

        # Re-enable the kind.
        resp = await auth_client.put(f"{_NODE_KINDS_URL}/script/enabled", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

        resp = await auth_client.get(_NODE_KINDS_URL)
        assert resp.json()["disabled_kinds"] == []

        resp = await auth_client.post(_VALIDATE_URL, json={"workflow_definition": _definition_with_script()})
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is True

    @pytest.mark.asyncio
    async def test_setting_row_is_updated(self, auth_client: AsyncClient, test_db_engine: AsyncEngine) -> None:
        """The switch is persisted in the runtime_settings row, not in memory."""
        resp = await auth_client.put(f"{_NODE_KINDS_URL}/http_request/enabled", json={"enabled": False})
        assert resp.status_code == 200

        async with test_db_engine.begin() as conn:
            row = (
                await conn.execute(
                    sqlalchemy.text("SELECT value FROM runtime_settings WHERE key = :key"),
                    {"key": DISABLED_NODE_KINDS_SETTING_KEY},
                )
            ).first()
        assert row is not None
        assert row[0] == ["http_request"]
