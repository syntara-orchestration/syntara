"""Exercise script Action reseeding against PostgreSQL."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.execution_plane.registry import seeder
from syntara.execution_plane.registry.models import ExecutionPlanePlugin

pytestmark = pytest.mark.integration


def _reference(repository: str, digest: str) -> str:
    return f"{repository}@sha256:{digest * 64}"


@pytest.mark.asyncio
async def test_seed_upserts_managed_images_and_preserves_an_administrator_pin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_db_session: AsyncSession,
) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(policy_path))
    monkeypatch.setattr(seeder, "verify_script_image_reference", Mock())

    python_a = _reference("registry.redhat.io/ansible-automation-platform/ao-python-rhel9", "a")
    bash_b = _reference("registry.redhat.io/ansible-automation-platform/ao-bash-rhel9", "b")
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_PYTHON", python_a)
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_BASH", bash_b)
    await seeder.seed_execution_plane_plugins(test_db_session)

    first_rows = (await test_db_session.exec(select(ExecutionPlanePlugin))).all()
    python_plugin = next(plugin for plugin in first_rows if plugin.name == "script-python")
    bash_plugin = next(plugin for plugin in first_rows if plugin.name == "script-bash")
    initial_ids = python_plugin.id, bash_plugin.id
    assert python_plugin.image_reference == python_a
    assert bash_plugin.image_reference == bash_b
    assert python_plugin.labels["managed_image_reference"] == python_a
    assert bash_plugin.labels["managed_image_reference"] == bash_b

    await seeder.seed_execution_plane_plugins(test_db_session)
    repeated_rows = (await test_db_session.exec(select(ExecutionPlanePlugin))).all()
    assert {plugin.name: plugin.id for plugin in repeated_rows} == {
        "script-python": initial_ids[0],
        "script-bash": initial_ids[1],
    }

    python_plugin.image_reference = _reference("registry.example/custom/ao-python", "c")
    test_db_session.add(python_plugin)
    await test_db_session.commit()
    python_d = _reference("registry.redhat.io/ansible-automation-platform/ao-python-rhel9", "d")
    bash_e = _reference("registry.redhat.io/ansible-automation-platform/ao-bash-rhel9", "e")
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_PYTHON", python_d)
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_BASH", bash_e)
    await seeder.seed_execution_plane_plugins(test_db_session)

    final_rows = (await test_db_session.exec(select(ExecutionPlanePlugin))).all()
    final_by_name = {plugin.name: plugin for plugin in final_rows}
    assert final_by_name["script-python"].id == initial_ids[0]
    assert final_by_name["script-python"].image_reference == _reference("registry.example/custom/ao-python", "c")
    assert final_by_name["script-bash"].id == initial_ids[1]
    assert final_by_name["script-bash"].image_reference == bash_e

    final_by_name["script-bash"].image_reference = "quay.io/aap/ansible-automation-platform/ao-bash-rhel9:devel"
    test_db_session.add(final_by_name["script-bash"])
    await test_db_session.commit()
    bash_f = _reference("registry.redhat.io/ansible-automation-platform/ao-bash-rhel9", "f")
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_PYTHON", python_d)
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_BASH", bash_f)
    await seeder.seed_execution_plane_plugins(test_db_session)

    upgraded_rows = (await test_db_session.exec(select(ExecutionPlanePlugin))).all()
    upgraded_by_name = {plugin.name: plugin for plugin in upgraded_rows}
    assert upgraded_by_name["script-bash"].id == initial_ids[1]
    assert upgraded_by_name["script-bash"].image_reference == bash_f


@pytest.mark.asyncio
async def test_http_seed_installs_dependencies_and_preserves_admin_pin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_db_session: AsyncSession,
) -> None:
    from syntara.execution_plane.registry.models import ExecutionPlaneCredentialRecipe, ExecutionPlaneIntegrationType

    policy = tmp_path / "policy.json"
    policy.write_text("{}")
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(policy))
    monkeypatch.setattr(seeder, "verify_script_image_reference", Mock())
    for name in ("SCRIPT_PYTHON", "SCRIPT_BASH", "HTTP_REQUEST"):
        monkeypatch.setenv(f"RELATED_IMAGE_{name}", _reference("registry.example/workload", "a"))
    await seeder.seed_execution_plane_plugins(test_db_session)
    first = (
        await test_db_session.exec(select(ExecutionPlanePlugin).where(ExecutionPlanePlugin.name == "http-request"))
    ).one()
    original_id = first.id
    first.image_reference = _reference("registry.example/admin-http", "b")
    test_db_session.add(first)
    await test_db_session.commit()
    monkeypatch.setenv("RELATED_IMAGE_HTTP_REQUEST", _reference("registry.example/workload", "c"))
    await seeder.seed_execution_plane_plugins(test_db_session)
    second = (
        await test_db_session.exec(select(ExecutionPlanePlugin).where(ExecutionPlanePlugin.name == "http-request"))
    ).one()
    assert second.id == original_id
    assert second.image_reference == _reference("registry.example/admin-http", "b")
    integration = (
        await test_db_session.exec(
            select(ExecutionPlaneIntegrationType).where(
                ExecutionPlaneIntegrationType.integration_type_id == "syntara.http"
            )
        )
    ).one()
    recipe = (
        await test_db_session.exec(
            select(ExecutionPlaneCredentialRecipe).where(
                ExecutionPlaneCredentialRecipe.credential_recipe_id == "syntara.http.bearer"
            )
        )
    ).one()
    assert recipe.integration_type_id == integration.integration_type_id
