"""Seed packaged Actions with configured workload images."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
import yaml
from sqlalchemy.dialects.postgresql import insert

from syntara.execution_plane.registry.models import (
    ExecutionPlaneCredentialRecipe,
    ExecutionPlaneIntegrationType,
    ExecutionPlanePlugin,
)
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
        "aap-workflow",
        NodeType.AAP_WORKFLOW_JOB_TEMPLATE,
        "syntara.aap-workflow.aap-workflow",
        "aap-workflow.yaml",
        "RELATED_IMAGE_AAP_WORKFLOW",
        "quay.io/aap/ansible-automation-platform/ao-aap-workflow-rhel9:devel",
    ),
)

# (integration_type_id, manifest name, filename)
_INTEGRATION_TYPE_SEEDS = (("syntara.aap", "aap", "integration-aap.yaml"),)

# (credential_recipe_id, integration_type_id, manifest name, filename)
_CREDENTIAL_RECIPE_SEEDS = (("syntara.aap.credential", "syntara.aap", "aap-credential", "credential-aap.yaml"),)


def _load_manifest(filename: str, expected_name: str, expected_kind: str = "Action") -> dict[str, Any]:
    """Load a packaged manifest and check its registry identity."""
    contents = files("syntara.execution_plane.registry.manifests").joinpath(filename).read_text(encoding="utf-8")
    manifest = yaml.safe_load(contents)
    if not isinstance(manifest, dict) or manifest.get("kind") != expected_kind:
        message = f"Packaged manifest {filename!r} is not a {expected_kind}"
        raise ValueError(message)
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("name") != expected_name:
        message = f"Packaged manifest {filename!r} has the wrong {expected_kind} name"
        raise ValueError(message)
    return manifest


async def seed_execution_plane_plugins(session: AsyncSession) -> None:
    """Seed packaged Actions, allowing the operator to override their image refs."""
    now = datetime.now(UTC)

    integration_rows = [
        {
            "id": uuid4(),
            "integration_type_id": integration_type_id,
            "manifest": _load_manifest(filename, name, "IntegrationType"),
            "created_at": now,
            "updated_at": now,
            "labels": {},
        }
        for integration_type_id, name, filename in _INTEGRATION_TYPE_SEEDS
    ]
    integration_statement = insert(ExecutionPlaneIntegrationType).values(integration_rows)
    integration_statement = integration_statement.on_conflict_do_update(
        index_elements=[ExecutionPlaneIntegrationType.integration_type_id],
        set_={
            "manifest": integration_statement.excluded.manifest,
            "updated_at": now,
        },
    )
    await session.exec(integration_statement)

    recipe_rows = [
        {
            "id": uuid4(),
            "credential_recipe_id": credential_recipe_id,
            "integration_type_id": integration_type_id,
            "manifest": _load_manifest(filename, name, "CredentialRecipe"),
            "created_at": now,
            "updated_at": now,
            "labels": {},
        }
        for credential_recipe_id, integration_type_id, name, filename in _CREDENTIAL_RECIPE_SEEDS
    ]
    recipe_statement = insert(ExecutionPlaneCredentialRecipe).values(recipe_rows)
    recipe_statement = recipe_statement.on_conflict_do_update(
        index_elements=[ExecutionPlaneCredentialRecipe.credential_recipe_id],
        set_={
            "integration_type_id": recipe_statement.excluded.integration_type_id,
            "manifest": recipe_statement.excluded.manifest,
            "updated_at": now,
        },
    )
    await session.exec(recipe_statement)

    rows = [
        {
            "id": uuid4(),
            "name": name,
            "node_type": node_type,
            "step_identity": step_identity,
            "manifest": _load_manifest(filename, name),
            "image_reference": os.environ.get(image_env_var) or image_reference,
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
