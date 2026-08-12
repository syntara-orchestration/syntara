"""Unit tests for workflow version serialization utility."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from syntara.workflows.utils.serialization import VersionPublishTimestamps, deserialize_workflow_version


class TestDeserializeWorkflowVersion:
    """Tests for deserialize_workflow_version status computation."""

    def _make_version(self, **overrides: object) -> MagicMock:
        version = MagicMock()
        version.id = overrides.get("id", uuid4())
        version.workflow_id = overrides.get("workflow_id", uuid4())
        version.version = overrides.get("version", 1)
        version.schema_version = overrides.get("schema_version", "2.0.0")
        version.workflow_definition = overrides.get("workflow_definition", {"nodes": []})
        version.change_description = overrides.get("change_description")
        version.name = overrides.get("name")
        version.created_by = overrides.get("created_by", uuid4())
        version.created_at = overrides.get("created_at", datetime.now(UTC))
        version.updated_at = overrides.get("updated_at", datetime.now(UTC))
        version.deleted_at = overrides.get("deleted_at")
        version.deleted_by = overrides.get("deleted_by")
        return version

    def test_draft_when_never_published(self) -> None:
        version = self._make_version()

        result = deserialize_workflow_version(version)

        assert result["status"] == "draft"

    def test_draft_when_not_in_ever_published_set(self) -> None:
        version = self._make_version()

        result = deserialize_workflow_version(
            version,
            workflow_published_version_id=uuid4(),
            ever_published_version_ids={uuid4()},
        )

        assert result["status"] == "draft"

    def test_published_when_id_matches(self) -> None:
        vid = uuid4()
        version = self._make_version(id=vid, name="Release v1")

        result = deserialize_workflow_version(version, workflow_published_version_id=vid)

        assert result["status"] == "published"
        assert result["name"] == "Release v1"

    def test_previously_published_when_in_ever_published_set(self) -> None:
        vid = uuid4()
        version = self._make_version(id=vid)

        result = deserialize_workflow_version(
            version,
            workflow_published_version_id=uuid4(),
            ever_published_version_ids={vid},
        )

        assert result["status"] == "previously_published"

    def test_published_takes_precedence_over_ever_published(self) -> None:
        vid = uuid4()
        version = self._make_version(id=vid)

        result = deserialize_workflow_version(
            version,
            workflow_published_version_id=vid,
            ever_published_version_ids={vid},
        )

        assert result["status"] == "published"

    def test_draft_when_no_workflow_published_version_id(self) -> None:
        version = self._make_version()

        result = deserialize_workflow_version(version)

        assert result["status"] == "draft"

    def test_all_fields_present(self) -> None:
        vid = uuid4()
        wfid = uuid4()
        uid = uuid4()
        now = datetime.now(UTC)
        version = self._make_version(
            id=vid,
            workflow_id=wfid,
            version=5,
            workflow_definition={"schema_version": "2.0.0"},
            change_description="Some change",
            name="v5-release",
            created_by=uid,
            created_at=now,
            updated_at=now,
        )

        result = deserialize_workflow_version(
            version,
            workflow_published_version_id=vid,
            ever_published_version_ids={vid},
        )

        assert result["id"] == vid
        assert result["workflow_id"] == wfid
        assert result["version"] == 5
        assert result["schema_version"] == "2.0.0"
        assert result["workflow_definition"] == {"schema_version": "2.0.0"}
        assert result["change_description"] == "Some change"
        assert result["name"] == "v5-release"
        assert result["created_by"] == uid
        assert result["created_at"] == now
        assert result["updated_at"] == now
        assert result["deleted_at"] is None
        assert result["deleted_by"] is None
        assert result["status"] == "published"

    def test_no_published_at_in_result(self) -> None:
        version = self._make_version()

        result = deserialize_workflow_version(version)

        assert "published_at" not in result


class TestDeserializePublishTimestamps:
    """Tests for last_published_at / last_unpublished_at suppression logic."""

    def _make_version(self, **overrides: object) -> MagicMock:
        version = MagicMock()
        version.id = overrides.get("id", uuid4())
        version.workflow_id = overrides.get("workflow_id", uuid4())
        version.version = overrides.get("version", 1)
        version.schema_version = overrides.get("schema_version", "2.0.0")
        version.workflow_definition = overrides.get("workflow_definition", {"nodes": []})
        version.change_description = overrides.get("change_description")
        version.name = overrides.get("name")
        version.created_by = overrides.get("created_by", uuid4())
        version.created_at = overrides.get("created_at", datetime.now(UTC))
        version.updated_at = overrides.get("updated_at", datetime.now(UTC))
        version.deleted_at = overrides.get("deleted_at")
        version.deleted_by = overrides.get("deleted_by")
        return version

    def test_last_unpublished_at_when_unpublished_after_published(self) -> None:
        """When unpublished_at > published_at, last_unpublished_at is returned."""
        vid = uuid4()
        version = self._make_version(id=vid)
        pub_time = datetime(2024, 1, 1, tzinfo=UTC)
        unpub_time = datetime(2024, 1, 2, tzinfo=UTC)
        ts = {vid: VersionPublishTimestamps(published_at=pub_time, unpublished_at=unpub_time)}

        result = deserialize_workflow_version(
            version, workflow_published_version_id=None, ever_published_version_ids={vid}, publish_timestamps=ts
        )

        assert result["last_unpublished_at"] == unpub_time

    def test_last_unpublished_at_none_when_republished(self) -> None:
        """When unpublished_at < published_at (re-published), last_unpublished_at is None."""
        vid = uuid4()
        version = self._make_version(id=vid)
        unpub_time = datetime(2024, 1, 1, tzinfo=UTC)
        pub_time = datetime(2024, 1, 2, tzinfo=UTC)
        ts = {vid: VersionPublishTimestamps(published_at=pub_time, unpublished_at=unpub_time)}

        result = deserialize_workflow_version(
            version, workflow_published_version_id=vid, ever_published_version_ids={vid}, publish_timestamps=ts
        )

        assert result["last_unpublished_at"] is None

    def test_last_unpublished_at_none_when_no_unpublish(self) -> None:
        """When unpublished_at is None, last_unpublished_at is None."""
        vid = uuid4()
        version = self._make_version(id=vid)
        pub_time = datetime(2024, 1, 1, tzinfo=UTC)
        ts = {vid: VersionPublishTimestamps(published_at=pub_time, unpublished_at=None)}

        result = deserialize_workflow_version(version, workflow_published_version_id=vid, publish_timestamps=ts)

        assert result["last_unpublished_at"] is None

    def test_last_unpublished_at_none_when_no_publish_but_unpublish_exists(self) -> None:
        """Defensive: when published_at is None but unpublished_at exists, last_unpublished_at is None."""
        vid = uuid4()
        version = self._make_version(id=vid)
        unpub_time = datetime(2024, 1, 1, tzinfo=UTC)
        ts = {vid: VersionPublishTimestamps(published_at=None, unpublished_at=unpub_time)}

        result = deserialize_workflow_version(version, publish_timestamps=ts)

        assert result["last_unpublished_at"] is None

    def test_last_published_at_returned_when_timestamps_exist(self) -> None:
        """last_published_at is always returned when publish timestamps exist."""
        vid = uuid4()
        version = self._make_version(id=vid)
        pub_time = datetime(2024, 1, 1, tzinfo=UTC)
        ts = {vid: VersionPublishTimestamps(published_at=pub_time)}

        result = deserialize_workflow_version(version, workflow_published_version_id=vid, publish_timestamps=ts)

        assert result["last_published_at"] == pub_time

    def test_last_published_at_none_when_no_timestamps(self) -> None:
        """last_published_at is None when no timestamps are provided."""
        version = self._make_version()

        result = deserialize_workflow_version(version)

        assert result["last_published_at"] is None

    def test_last_published_at_none_when_version_not_in_timestamps(self) -> None:
        """last_published_at is None when the version has no entry in timestamps dict."""
        version = self._make_version()
        other_id = uuid4()
        ts = {other_id: VersionPublishTimestamps(published_at=datetime.now(UTC))}

        result = deserialize_workflow_version(version, publish_timestamps=ts)

        assert result["last_published_at"] is None
