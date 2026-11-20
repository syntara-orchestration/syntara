"""Seed SDK Action manifests with configured workload images."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
import yaml
from sqlalchemy.dialects.postgresql import insert

from syntara.core.config.base import get_settings
from syntara.execution_plane.registry.models import ExecutionPlanePlugin
from syntara.workflow_core.models import NodeType

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

_PLUGIN_SEEDS = (
    (
        "script-python",
        NodeType.SCRIPT_PYTHON,
        "syntara.script-python.script-python",
        "script-python.yaml",
        "RELATED_IMAGE_SCRIPT_PYTHON",
        "quay.io/aap/ansible-automation-platform/ao-python-rhel9:devel",
    ),
    (
        "script-bash",
        NodeType.SCRIPT_BASH,
        "syntara.script-bash.script-bash",
        "script-bash.yaml",
        "RELATED_IMAGE_SCRIPT_BASH",
        "quay.io/aap/ansible-automation-platform/ao-bash-rhel9:devel",
    ),
    (
        "agent-runtime",
        NodeType.AGENTIC,
        "syntara.agent-runtime.agent-runtime",
        "agent-runtime.yaml",
        None,
        "quay.io/aap/ansible-automation-platform/ao-agent-runtime:devel",
    ),
)


def _load_manifest(filename: str, expected_name: str) -> dict[str, Any]:
    """Load a packaged Action manifest and check its registry identity."""
    contents = files("syntara.execution_plane.registry.manifests").joinpath(filename).read_text(encoding="utf-8")
    manifest = yaml.safe_load(contents)
    if not isinstance(manifest, dict) or manifest.get("kind") != "Action":
        message = f"Packaged plugin manifest {filename!r} is not an Action"
        raise ValueError(message)
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("name") != expected_name:
        message = f"Packaged plugin manifest {filename!r} has the wrong Action name"
        raise ValueError(message)
    return manifest


async def seed_execution_plane_plugins(session: AsyncSession) -> None:
    """Idempotently seed SDK Actions, applying configured image overrides."""
    now = datetime.now(UTC)
    rows = [
        {
            "id": uuid4(),
            "name": name,
            "node_type": node_type,
            "step_identity": step_identity,
            "manifest": _load_manifest(filename, name),
            "image_reference": (
                get_settings().agent_runtime_image
                if name == "agent-runtime"
                else os.environ.get(image_env_var) or image_reference
            ),
            "created_at": now,
            "updated_at": now,
            "labels": {},
        }
        for name, node_type, step_identity, filename, image_env_var, image_reference in _PLUGIN_SEEDS
    ]
    statement = insert(ExecutionPlanePlugin).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[ExecutionPlanePlugin.name],
        set_={
            "step_identity": statement.excluded.step_identity,
            "node_type": statement.excluded.node_type,
            "manifest": statement.excluded.manifest,
            "image_reference": statement.excluded.image_reference,
            "updated_at": now,
        },
    )
    await session.exec(statement)
    await session.commit()
    logger.info("execution_plane_plugins.seeded", count=len(rows))
