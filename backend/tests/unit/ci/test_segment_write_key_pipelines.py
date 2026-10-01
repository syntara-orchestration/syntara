"""The production Segment write key belongs only on customer-facing builds.

Konflux exposes ``additional-secret`` to the image build as a Buildah secret.
Pull-request images are ephemeral CI artifacts, and the devel push image is what
the internal nexus-devel environment runs. Neither may receive
``nexus-segment-write-keys``. The early-access push image is the customer-facing
channel (OLM ``early-access``, published toward registry.redhat.io) and must
still mount that secret. The Containerfile must read it only when the secret is
present so internal builds keep working with telemetry disabled.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
TEKTON_DIR = REPO_ROOT / ".tekton"
CONTAINERFILE = REPO_ROOT / "backend" / "containers" / "syntara" / "Containerfile"

SEGMENT_WRITE_KEYS_RESOURCE = "nexus-segment-write-keys"
CUSTOMER_FACING_PIPELINE = "ansible-automation-orchestrator-backend-early-access-push.yaml"


def _pipeline(name: str) -> dict:
    return yaml.safe_load((TEKTON_DIR / name).read_text())


def _param(pipeline: dict, name: str) -> str | None:
    for param in pipeline["spec"]["params"]:
        if param["name"] == name:
            value = param["value"]
            assert isinstance(value, str)
            return value
    return None


def _cel(pipeline: dict) -> str:
    return pipeline["metadata"]["annotations"]["pipelinesascode.tekton.dev/on-cel-expression"]


def test_prod_segment_secret_is_not_on_internal_builds() -> None:
    """Internal and pull-request pipelines must not mount the production Segment secret."""
    offenders = sorted(
        path.name
        for path in TEKTON_DIR.glob("*.yaml")
        if path.name != CUSTOMER_FACING_PIPELINE and SEGMENT_WRITE_KEYS_RESOURCE in path.read_text()
    )
    assert offenders == []


def test_customer_facing_early_access_push_mounts_prod_segment_secret() -> None:
    """The early-access push image is the customer-facing build and keeps the prod secret."""
    pipeline = _pipeline(CUSTOMER_FACING_PIPELINE)
    cel = _cel(pipeline)
    assert 'event == "push"' in cel
    assert 'target_branch == "early-access"' in cel
    assert _param(pipeline, "image-expires-after") is None
    assert _param(pipeline, "additional-secret") == SEGMENT_WRITE_KEYS_RESOURCE


def test_containerfile_reads_prod_segment_secret_only_when_mounted() -> None:
    """Missing secret must not fail internal builds, and the key must not be hardcoded."""
    text = CONTAINERFILE.read_text()
    assert "id=nexus-segment-write-keys/SEGMENT_WRITE_KEY_DEV,required=false" in text
    assert 'ARG APP_SEGMENT_WRITE_KEY=""' in text
    assert 'ENV APP_SEGMENT_WRITE_KEY="${APP_SEGMENT_WRITE_KEY}"' not in text
