"""Seed the Python and Bash Action manifests and their devel workload images."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
import yaml
from sqlalchemy.dialects.postgresql import insert

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
        "quay.io/aap/ansible-automation-platform/ao-python-rhel9:devel",
    ),
    (
        "script-bash",
        NodeType.SCRIPT_BASH,
        "syntara.script-bash.script-bash",
        "script-bash.yaml",
        "quay.io/aap/ansible-automation-platform/ao-bash-rhel9:devel",
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
    """Idempotently seed the two script Actions and their devel image refs."""
    now = datetime.now(UTC)
    rows = [
        {
            "id": uuid4(),
            "name": name,
            "node_type": node_type,
            "step_identity": step_identity,
            "manifest": _load_manifest(filename, name),
            "image_reference": image_reference,
            "created_at": now,
            "updated_at": now,
            "labels": {},
        }
        for name, node_type, step_identity, filename, image_reference in _PLUGIN_SEEDS
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
