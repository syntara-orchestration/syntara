"""HTTP registry assets and image approval requirements."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from syntara.execution_plane.registry import seeder
from syntara.execution_plane.registry.image_policy import _ACTION_IDENTITIES
from syntara.workflow_core.models import NodeType


def test_http_action_matches_container_identity() -> None:
    manifest = seeder._load_manifest("http-request.yaml", "http-request")
    assert manifest["spec"]["integrationType"] == "syntara.http"
    assert _ACTION_IDENTITIES[NodeType.HTTP_REQUEST] == "syntara.http-request.http-request"


@pytest.mark.asyncio
async def test_http_dependency_assets_are_seeded_in_order_without_committing() -> None:
    session = AsyncMock()
    await seeder._seed_http_credentials(session)
    statements = [
        cast("Any", call.args[0]).compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
        for call in session.exec.await_args_list
    ]
    assert len(statements) == 2
    assert statements[0].params["integration_type_id"] == "syntara.http"
    assert statements[1].params["credential_recipe_id"] == "syntara.http.bearer"
    assert statements[1].params["integration_type_id"] == "syntara.http"
    assert all("ON CONFLICT" in str(statement) for statement in statements)
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_policy_failure_prevents_all_seed_writes(monkeypatch, tmp_path) -> None:
    from unittest.mock import Mock

    from syntara.execution_plane.registry.image_policy import ScriptImagePolicyError

    policy = tmp_path / "policy.json"
    policy.write_text("{}")
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(policy))
    for name in ("SCRIPT_PYTHON", "SCRIPT_BASH", "HTTP_REQUEST"):
        monkeypatch.setenv(f"RELATED_IMAGE_{name}", "registry.example/workload@sha256:" + "a" * 64)
    monkeypatch.setattr(
        seeder,
        "verify_script_image_reference",
        Mock(side_effect=[None, None, ScriptImagePolicyError("HTTP not approved")]),
    )
    session = AsyncMock()
    with pytest.raises(ScriptImagePolicyError, match="HTTP not approved"):
        await seeder.seed_execution_plane_plugins(session)
    session.exec.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_http_image_uses_valid_false_update_guard(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    policy = tmp_path / "policy.json"
    policy.write_text("{}")
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(policy))
    reference = "registry.example/workload@sha256:" + "a" * 64
    for name in ("SCRIPT_PYTHON", "SCRIPT_BASH", "HTTP_REQUEST"):
        monkeypatch.setenv(f"RELATED_IMAGE_{name}", reference)
    monkeypatch.setattr(seeder, "verify_script_image_reference", Mock())
    session = AsyncMock()
    empty = Mock()
    empty.all.return_value = []
    persisted = Mock()
    persisted.all.return_value = [
        SimpleNamespace(name=name, image_reference=reference)
        for name in ("script-python", "script-bash", "http-request")
    ]
    session.exec.side_effect = [empty, Mock(), Mock(), Mock(), Mock(), Mock(), persisted]
    await seeder.seed_execution_plane_plugins(session)
    http_insert = cast("Any", session.exec.await_args_list[3].args[0]).compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    assert "CASE WHEN false" in str(http_insert)
    assert http_insert.params["name"] == "http-request"
    session.commit.assert_awaited_once()
