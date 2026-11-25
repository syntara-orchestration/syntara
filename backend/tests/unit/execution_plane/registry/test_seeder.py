"""Tests for secure, repeatable script Action seeding."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from syntara.execution_plane.registry import seeder
from syntara.execution_plane.registry.image_policy import ScriptImagePolicyError

_PYTHON_REFERENCE = "registry.redhat.io/ansible-automation-platform/ao-python-rhel9@sha256:" + "a" * 64
_BASH_REFERENCE = "registry.redhat.io/ansible-automation-platform/ao-bash-rhel9@sha256:" + "b" * 64


def _install_policy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(policy_path))


@pytest.mark.asyncio
async def test_seed_requires_verified_digest_images_and_preserves_administrator_pins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_policy(monkeypatch, tmp_path)
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_PYTHON", _PYTHON_REFERENCE)
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_BASH", _BASH_REFERENCE)
    verify = Mock()
    monkeypatch.setattr(seeder, "verify_script_image_reference", verify)
    session = AsyncMock()

    def result_for(plugins: list[object]) -> Mock:
        result = Mock()
        result.all.return_value = plugins
        return result

    session.exec.side_effect = [
        result_for([]),
        result_for([]),
        result_for([]),
        result_for(
            [
                SimpleNamespace(name="script-python", image_reference=_PYTHON_REFERENCE),
                SimpleNamespace(name="script-bash", image_reference=_BASH_REFERENCE),
            ]
        ),
    ]

    await seeder.seed_execution_plane_plugins(session)

    assert verify.call_count == 2
    compiled_statements = [
        cast("Any", call.args[0]).compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
        for call in session.exec.await_args_list[1:3]
    ]
    compiled = "\n".join(map(str, compiled_statements))
    parameters = str([compiled_statement.params for compiled_statement in compiled_statements])
    assert "ON CONFLICT (name) DO UPDATE" in compiled
    assert "CASE" in compiled
    assert "managed_image_reference" in parameters
    assert "jsonb_set" in compiled
    assert "ao-python-rhel9:devel" in parameters
    assert "ao-bash-rhel9:devel" in parameters
    assert "ao-python-rhel9:2026.8" in parameters
    assert "ao-bash-rhel9:2026.8" in parameters
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_verifies_both_actions_before_writing_any_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_policy(monkeypatch, tmp_path)
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_PYTHON", _PYTHON_REFERENCE)
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_BASH", _BASH_REFERENCE)
    verify = Mock(side_effect=[None, ScriptImagePolicyError("unapproved bash image")])
    monkeypatch.setattr(seeder, "verify_script_image_reference", verify)
    session = AsyncMock()

    with pytest.raises(ScriptImagePolicyError, match="unapproved bash image"):
        await seeder.seed_execution_plane_plugins(session)

    assert verify.call_count == 2
    session.exec.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_rejects_missing_image_reference_before_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_policy(monkeypatch, tmp_path)
    monkeypatch.delenv("RELATED_IMAGE_SCRIPT_PYTHON", raising=False)
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_BASH", _BASH_REFERENCE)
    session = AsyncMock()

    with pytest.raises(ValueError, match="RELATED_IMAGE_SCRIPT_PYTHON"):
        await seeder.seed_execution_plane_plugins(session)

    session.exec.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_leaves_script_actions_unavailable_without_installed_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_PYTHON", _PYTHON_REFERENCE)
    monkeypatch.setenv("RELATED_IMAGE_SCRIPT_BASH", _BASH_REFERENCE)
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(tmp_path / "missing-policy.json"))
    session = AsyncMock()

    await seeder.seed_execution_plane_plugins(session)

    session.exec.assert_not_awaited()
    session.commit.assert_not_awaited()
