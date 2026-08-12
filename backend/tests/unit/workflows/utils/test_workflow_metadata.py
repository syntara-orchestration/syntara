"""Tests for build_workflow_metadata.

Ensures the nested dict structure consumed by DynamicWorkflow._initialize_state
is correct, with UUIDs stringified and all fields in the right positions.
"""

from typing import Any
from uuid import uuid4

import pytest

from syntara.workflows.utils.workflow_metadata import build_workflow_metadata


def _build(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build metadata with sensible defaults, allowing per-test overrides."""
    defaults: dict[str, Any] = {
        "workflow_name": "my-workflow",
        "workflow_id": uuid4(),
        "workflow_version": 3,
        "workflow_published": True,
        "workflow_author": "alice",
        "project_id": uuid4(),
        "execution_id": "exec-123",
        "execution_mode": "standard",
        "created_by": "bob",
        "created_by_user_id": "user-123",
        "created_at": "2024-01-01T00:00:00Z",
        "workflow_version_id": uuid4(),
    }
    return build_workflow_metadata(**{**defaults, **overrides})


class TestStructure:
    """The returned dict has the exact shape DynamicWorkflow expects."""

    def test_top_level_key(self) -> None:
        result = _build()
        assert list(result.keys()) == ["workflow_context"]

    def test_workflow_context_keys(self) -> None:
        ctx = _build()["workflow_context"]
        assert set(ctx.keys()) == {"workflow", "execution"}

    def test_workflow_fields(self) -> None:
        wf = _build()["workflow_context"]["workflow"]
        assert set(wf.keys()) == {"name", "id", "version", "published", "author", "project_id"}

    def test_execution_fields(self) -> None:
        ex = _build()["workflow_context"]["execution"]
        assert set(ex.keys()) == {"id", "mode", "created_by", "created_by_user_id", "created_at", "workflow_version_id"}


class TestUuidStringification:
    """UUID inputs are converted to strings in the output."""

    def test_project_id_is_string(self) -> None:
        pid = uuid4()
        result = _build(project_id=pid)
        assert result["workflow_context"]["workflow"]["project_id"] == str(pid)

    def test_workflow_id_is_string(self) -> None:
        wid = uuid4()
        result = _build(workflow_id=wid)
        assert result["workflow_context"]["workflow"]["id"] == str(wid)

    def test_workflow_version_id_is_string(self) -> None:
        vid = uuid4()
        result = _build(workflow_version_id=vid)
        assert result["workflow_context"]["execution"]["workflow_version_id"] == str(vid)


class TestFieldPassthrough:
    """Scalar values are passed through unchanged."""

    def test_workflow_name(self) -> None:
        assert _build(workflow_name="foo")["workflow_context"]["workflow"]["name"] == "foo"

    def test_workflow_version(self) -> None:
        assert _build(workflow_version=7)["workflow_context"]["workflow"]["version"] == 7

    def test_published_flag(self) -> None:
        assert _build(workflow_published=False)["workflow_context"]["workflow"]["published"] is False

    def test_author(self) -> None:
        assert _build(workflow_author="eve")["workflow_context"]["workflow"]["author"] == "eve"

    def test_created_by(self) -> None:
        assert _build(created_by="system")["workflow_context"]["execution"]["created_by"] == "system"

    def test_created_by_user_id(self) -> None:
        assert _build(created_by_user_id="uid-456")["workflow_context"]["execution"]["created_by_user_id"] == "uid-456"

    def test_created_at(self) -> None:
        ts = "2026-07-09T12:00:00Z"
        assert _build(created_at=ts)["workflow_context"]["execution"]["created_at"] == ts

    @pytest.mark.parametrize("mode", ["standard", "test", "scheduled"])
    def test_execution_mode(self, mode: str) -> None:
        assert _build(execution_mode=mode)["workflow_context"]["execution"]["mode"] == mode


class TestDynamicWorkflowCompat:
    """Output is compatible with DynamicWorkflow._initialize_state unpacking.

    _initialize_state does:
        wf_ctx = metadata.get("workflow_context", {}).get("workflow", {})
        self._project_id = wf_ctx.get("project_id", "")

    A valid metadata dict must produce a non-empty project_id through this path.
    """

    def test_project_id_extractable(self) -> None:
        pid = uuid4()
        result = _build(project_id=pid)
        extracted = result.get("workflow_context", {}).get("workflow", {}).get("project_id", "")
        assert extracted == str(pid)
        assert extracted != ""
