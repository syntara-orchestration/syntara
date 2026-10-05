"""The production Segment write key is not baked into container images.

Konflux ``additional-secret`` would expose the production Segment secret to the
image build. Copying that value into a layer or an image environment variable
lets anyone who can pull the image read it. Telemetry stays configured at
runtime through ``APP_SEGMENT_WRITE_KEY``.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
TEKTON_DIR = REPO_ROOT / ".tekton"
CONTAINERFILE = REPO_ROOT / "backend" / "containers" / "syntara" / "Containerfile"

SEGMENT_WRITE_KEYS_RESOURCE = "nexus-segment-write-keys"


def test_pipelines_do_not_mount_prod_segment_secret() -> None:
    """No Konflux pipeline mounts the production Segment secret."""
    offenders = sorted(
        path.name for path in TEKTON_DIR.glob("*.yaml") if SEGMENT_WRITE_KEYS_RESOURCE in path.read_text()
    )
    assert offenders == []


def test_containerfile_does_not_bake_segment_write_key() -> None:
    """The image build must not copy the write key into a layer or image config."""
    text = CONTAINERFILE.read_text()
    assert SEGMENT_WRITE_KEYS_RESOURCE not in text
    assert "SEGMENT_WRITE_KEY" not in text
    assert "APP_SEGMENT_WRITE_KEY" not in text
    assert "/opt/app-root/src/.env" not in text
