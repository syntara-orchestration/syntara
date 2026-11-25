"""Validation and Cosign verification for script workload images."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Final, NoReturn

from syntara.workflow_core.models import NodeType

_REGISTRY_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
_REGISTRY = rf"(?:{_REGISTRY_LABEL}(?:\.{_REGISTRY_LABEL})*)(?::[1-9][0-9]{{0,4}})?"
_REPOSITORY_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
_IMAGE_REFERENCE: Final = re.compile(
    rf"^(?P<repository>{_REGISTRY}/{_REPOSITORY_COMPONENT}(?:/{_REPOSITORY_COMPONENT})*)"
    r"@sha256:(?P<digest>[a-f0-9]{64})$"
)
_ACTION_IDENTITIES: Final[dict[NodeType, str]] = {
    NodeType.SCRIPT_PYTHON: "syntara.script-python.script-python",
    NodeType.SCRIPT_BASH: "syntara.script-bash.script-bash",
}
_POLICY_PATH_ENV = "APP_SCRIPT_IMAGE_POLICY_PATH"
_COSIGN_TIMEOUT_SECONDS = 120


class ScriptImagePolicyError(ValueError):
    """A script image is not pinned, approved, or signed by its configured publisher."""


def script_image_digest(reference: str) -> str | None:
    """Return the digest for a valid fully-qualified script image reference."""
    match = _IMAGE_REFERENCE.fullmatch(reference)
    return match.group("digest") if match else None


def _raise_policy_error(message: str) -> NoReturn:
    raise ScriptImagePolicyError(message)


def _load_policy() -> dict[str, Any]:
    policy_path = os.environ.get(_POLICY_PATH_ENV)
    if not policy_path:
        message = f"{_POLICY_PATH_ENV} must point to the installed script image policy"
        _raise_policy_error(message)
    try:
        policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        message = "Installed script image policy could not be read"
        raise ScriptImagePolicyError(message) from error
    if not isinstance(policy, dict) or policy.get("version") != 1 or not isinstance(policy.get("actions"), dict):
        _raise_policy_error("Installed script image policy has an unsupported format")
    return policy


def _approved_reference_and_key(node_type: NodeType, reference: str) -> Path:
    if _IMAGE_REFERENCE.fullmatch(reference) is None:
        _raise_policy_error("Script workload images must use repository@sha256:<64 lowercase hex digits>")

    identity = _ACTION_IDENTITIES.get(node_type)
    policy = _load_policy()
    action_policy = policy["actions"].get(identity) if identity else None
    approved_reference = action_policy.get("image_reference") if isinstance(action_policy, dict) else None
    key_file = action_policy.get("key_file") if isinstance(action_policy, dict) else None
    if approved_reference != reference:
        message = f"Image reference is not approved for {node_type.value}"
        _raise_policy_error(message)
    if not isinstance(key_file, str) or Path(key_file).name != key_file:
        _raise_policy_error("No valid Cosign verification key is configured for the approved image")

    policy_path = Path(os.environ[_POLICY_PATH_ENV]).resolve()
    key_path = (policy_path.parent / key_file).resolve()
    if not key_path.is_relative_to(policy_path.parent) or not key_path.is_file():
        _raise_policy_error("Configured Cosign verification key is unavailable")
    return key_path


def validate_script_image_reference(node_type: NodeType, reference: str) -> str:
    """Require a digest-pinned image to match this Action's exact installed approval."""
    _approved_reference_and_key(node_type, reference)
    return reference


def verify_script_image_reference(node_type: NodeType, reference: str) -> None:
    """Require the exact approved Action image to have a valid Cosign signature."""
    key_path = _approved_reference_and_key(node_type, reference)
    cosign = shutil.which("cosign")
    if cosign is None:
        _raise_policy_error("Cosign is required to verify script workload images")

    try:
        result = subprocess.run(  # noqa: S603 - executable is the installed Cosign binary; arguments are validated
            [cosign, "verify", f"--key={key_path}", reference],
            capture_output=True,
            check=False,
            shell=False,
            timeout=_COSIGN_TIMEOUT_SECONDS,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        message = "Cosign could not verify the script workload image"
        raise ScriptImagePolicyError(message) from error
    if result.returncode != 0:
        _raise_policy_error("Script workload image signature verification failed")
