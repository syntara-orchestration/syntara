"""Konflux builds must not mount the production Segment secret.

The image still accepts the write key as a build argument and publishes it as
``APP_SEGMENT_WRITE_KEY``. The default is empty, so a build that does not pass
the argument does not carry the production key. The key must not be copied
from ``nexus-segment-write-keys`` into an image layer.
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


def test_containerfile_passes_segment_write_key_only_as_build_arg() -> None:
    """The image publishes APP_SEGMENT_WRITE_KEY from a build-arg, defaulting to empty."""
    text = CONTAINERFILE.read_text()
    assert 'ARG APP_SEGMENT_WRITE_KEY=""' in text
    assert 'APP_SEGMENT_WRITE_KEY="${APP_SEGMENT_WRITE_KEY}"' in text
    assert SEGMENT_WRITE_KEYS_RESOURCE not in text
    assert "SEGMENT_WRITE_KEY_DEV" not in text
    assert "/opt/app-root/src/.env" not in text
