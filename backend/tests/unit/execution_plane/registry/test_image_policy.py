"""Tests for script workload image policy enforcement."""

from __future__ import annotations

import json
import shutil
import subprocess
from subprocess import CompletedProcess
from typing import TYPE_CHECKING

import pytest

from syntara.execution_plane.registry import image_policy
from syntara.workflow_core.models import NodeType

if TYPE_CHECKING:
    from pathlib import Path

_PYTHON_REFERENCE = "quay.io/aap/ansible-automation-platform/ao-python-rhel9@sha256:" + "a" * 64
_BASH_REFERENCE = "registry.redhat.io/ansible-automation-platform/ao-bash-rhel9@sha256:" + "b" * 64


def _write_policy(path: Path) -> Path:
    (path / "python.pub").write_text("test public key", encoding="utf-8")
    (path / "bash.pub").write_text("test public key", encoding="utf-8")
    policy_path = path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "actions": {
                    "syntara.script-python.script-python": {
                        "image_reference": _PYTHON_REFERENCE,
                        "key_file": "python.pub",
                    },
                    "syntara.script-bash.script-bash": {
                        "image_reference": _BASH_REFERENCE,
                        "key_file": "bash.pub",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return policy_path


@pytest.mark.parametrize(
    ("node_type", "reference"),
    [(NodeType.SCRIPT_PYTHON, _PYTHON_REFERENCE), (NodeType.SCRIPT_BASH, _BASH_REFERENCE)],
)
def test_validate_script_image_reference_accepts_action_repository_digest(
    node_type: NodeType, reference: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(_write_policy(tmp_path)))
    assert image_policy.validate_script_image_reference(node_type, reference) == reference


@pytest.mark.parametrize(
    ("node_type", "reference"),
    [
        (NodeType.SCRIPT_PYTHON, "quay.io/aap/ansible-automation-platform/ao-python-rhel9:devel"),
        (NodeType.SCRIPT_PYTHON, _BASH_REFERENCE),
        (NodeType.SCRIPT_BASH, "quay.io/unapproved/image@sha256:" + "c" * 64),
        (NodeType.SCRIPT_BASH, "registry.redhat.io/ansible-automation-platform/ao-bash-rhel9@sha256:" + "Z" * 64),
    ],
)
def test_validate_script_image_reference_rejects_tags_and_unapproved_repositories(
    node_type: NodeType, reference: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(_write_policy(tmp_path)))
    with pytest.raises(image_policy.ScriptImagePolicyError):
        image_policy.validate_script_image_reference(node_type, reference)


def test_verify_script_image_reference_uses_registry_key_and_cosign(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_path = tmp_path / "python.pub"
    policy_path = _write_policy(tmp_path)
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(policy_path))
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/cosign")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(arguments: list[str], **kwargs: object) -> CompletedProcess[str]:
        calls.append((arguments, kwargs))
        return CompletedProcess(arguments, 0, "verified", "")

    monkeypatch.setattr(subprocess, "run", run)

    image_policy.verify_script_image_reference(NodeType.SCRIPT_PYTHON, _PYTHON_REFERENCE)

    assert calls[0][0] == ["/usr/bin/cosign", "verify", f"--key={key_path}", _PYTHON_REFERENCE]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] == 120


def test_verify_script_image_reference_fails_closed_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_SCRIPT_IMAGE_POLICY_PATH", raising=False)

    with pytest.raises(image_policy.ScriptImagePolicyError, match="APP_SCRIPT_IMAGE_POLICY_PATH"):
        image_policy.verify_script_image_reference(NodeType.SCRIPT_PYTHON, _PYTHON_REFERENCE)


def test_verify_script_image_reference_hides_cosign_output_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    policy_path = _write_policy(tmp_path)
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(policy_path))
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/cosign")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda arguments, **_kwargs: CompletedProcess(arguments, 1, "", "registry credentials"),
    )

    with pytest.raises(image_policy.ScriptImagePolicyError, match="signature verification failed") as error:
        image_policy.verify_script_image_reference(NodeType.SCRIPT_PYTHON, _PYTHON_REFERENCE)

    assert "registry credentials" not in str(error.value)


def test_validate_script_image_reference_rejects_digest_not_in_exact_action_approval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_SCRIPT_IMAGE_POLICY_PATH", str(_write_policy(tmp_path)))
    unapproved_digest = _PYTHON_REFERENCE[:-1] + "c"

    with pytest.raises(image_policy.ScriptImagePolicyError, match="not approved"):
        image_policy.validate_script_image_reference(NodeType.SCRIPT_PYTHON, unapproved_digest)
