"""Seed Python and Bash Actions with configured workload images."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any
from typing import cast as typing_cast
from uuid import uuid4

import structlog
import yaml
from sqlalchemy import ARRAY, Text, case, cast, func, or_
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlmodel import select

from syntara.execution_plane.registry.image_policy import script_image_digest, verify_script_image_reference
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
    ),
    (
        "script-bash",
        NodeType.SCRIPT_BASH,
        "syntara.script-bash.script-bash",
        "script-bash.yaml",
        "RELATED_IMAGE_SCRIPT_BASH",
    ),
)
_LEGACY_SEED_REFERENCES = {
    "script-python": ("quay.io/aap/ansible-automation-platform/ao-python-rhel9:devel",),
    "script-bash": ("quay.io/aap/ansible-automation-platform/ao-bash-rhel9:devel",),
}


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
    """Seed verified script Actions without replacing an administrator's image pin."""
    policy_path = os.environ.get("APP_SCRIPT_IMAGE_POLICY_PATH")
    if not policy_path or not await asyncio.to_thread(Path(policy_path).is_file):
        logger.warning("execution_plane_plugins.unavailable", reason="script_image_policy_not_installed")
        return

    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for name, node_type, step_identity, filename, image_env_var in _PLUGIN_SEEDS:
        image_reference = os.environ.get(image_env_var)
        if not image_reference:
            message = f"{image_env_var} must contain the approved script workload image reference"
            raise ValueError(message)
        await asyncio.to_thread(verify_script_image_reference, node_type, image_reference)
        rows.append(
            {
                "id": uuid4(),
                "name": name,
                "node_type": node_type,
                "step_identity": step_identity,
                "manifest": _load_manifest(filename, name),
                "image_reference": image_reference,
                "created_at": now,
                "updated_at": now,
                "labels": {"managed_image_reference": image_reference},
            }
        )
    existing_plugins = {
        plugin.name: plugin
        for plugin in (await session.exec(select(ExecutionPlanePlugin).execution_options(populate_existing=True))).all()
    }
    for row in rows:
        statement = insert(ExecutionPlanePlugin).values(row)
        name = row["name"]
        existing_plugin = existing_plugins.get(name)
        managed_references = []
        if existing_plugin is not None and existing_plugin.image_reference == existing_plugin.labels.get(
            "managed_image_reference"
        ):
            # Compare against the value read above so a concurrent pin change is preserved.
            managed_references.append(
                typing_cast("Any", ExecutionPlanePlugin.image_reference) == existing_plugin.image_reference
            )
        legacy_image_references = [
            typing_cast("Any", ExecutionPlanePlugin.image_reference) == legacy_reference
            for legacy_reference in _LEGACY_SEED_REFERENCES.get(name, ())
        ]
        can_advance_managed_reference = or_(*managed_references, *legacy_image_references)
        labels_with_managed_reference = func.jsonb_set(
            func.coalesce(ExecutionPlanePlugin.labels, cast({}, JSONB)),
            cast(["managed_image_reference"], ARRAY(Text)),
            statement.excluded.labels["managed_image_reference"],
            True,  # noqa: FBT003 - jsonb_set's final PostgreSQL argument is create_if_missing
        )
        statement = statement.on_conflict_do_update(
            index_elements=[ExecutionPlanePlugin.name],
            set_={
                "step_identity": statement.excluded.step_identity,
                "node_type": statement.excluded.node_type,
                "manifest": statement.excluded.manifest,
                "image_reference": case(
                    (can_advance_managed_reference, statement.excluded.image_reference),
                    else_=ExecutionPlanePlugin.image_reference,
                ),
                "labels": case(
                    (can_advance_managed_reference, labels_with_managed_reference), else_=ExecutionPlanePlugin.labels
                ),
                "updated_at": now,
            },
        )
        await session.exec(statement)
    await session.commit()
    persisted_plugins = {
        plugin.name: plugin
        for plugin in (await session.exec(select(ExecutionPlanePlugin).execution_options(populate_existing=True))).all()
    }
    for row in rows:
        name = row["name"]
        old_plugin = existing_plugins.get(name)
        persisted_plugin = persisted_plugins[name]
        if old_plugin is None:
            disposition = "inserted"
        elif persisted_plugin.image_reference == row["image_reference"]:
            disposition = "managed_reference_applied"
        else:
            disposition = "administrator_pin_preserved"
        logger.info(
            "execution_plane_plugins.image_seeded",
            action=name,
            old_digest=script_image_digest(old_plugin.image_reference) if old_plugin else None,
            new_digest=script_image_digest(persisted_plugin.image_reference),
            candidate_digest=script_image_digest(row["image_reference"]),
            disposition=disposition,
        )
    logger.info("execution_plane_plugins.seeded", count=len(rows))
