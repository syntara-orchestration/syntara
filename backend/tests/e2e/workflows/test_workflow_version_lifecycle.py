"""End-to-end tests for workflow version lifecycle.

Covers test plan cases: API-4 (republish), API-5 (idempotent republish),
API-6 (unpublish), API-7 (unpublish 400), API-8 (publish 404),
API-11 (manual run unpublished), API-13 (restore no-op), API-14 (restore 404),
API-16 (export 404), API-17 (version name edge cases), API-19 (conflict 409),
API-23 (in-flight execution continues on original version).

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from orchestrator_test_sdk.e2e.helpers import poll_execution
from syntara_api_client.models.execution_create import ExecutionCreate
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.publish_version_request import PublishVersionRequest
from syntara_api_client.models.workflow_definition import WorkflowDefinition
from syntara_api_client.models.workflow_update import WorkflowUpdate

if TYPE_CHECKING:
    from uuid import UUID

    from orchestrator_test_sdk.factories.workflows import WorkflowFactory
    from syntara_api_client.api import SyntaraApiRegistry

pytestmark = [pytest.mark.e2e]


def _simple_definition(activity_id: str = "task1", description: str = "v1") -> WorkflowDefinition:
    return WorkflowDefinition.from_dict(
        {
            "schema_version": "2.0.0",
            "name": "e2e-lifecycle",
            "description": description,
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": activity_id,
                    "name": activity_id,
                    "type": "script",
                    "parameters": {"language": "python", "code": f'print("{description}")'},
                },
            ],
            "edges": [{"from": "trigger", "to": activity_id}],
        }
    )


class TestPublishLifecycle:
    """E2E tests for publish/unpublish lifecycle (API-4 through API-8)."""

    def test_republish_previously_published_version(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-4: Publish v1 -> publish v2 -> re-publish v1. v1 becomes published again."""
        wf_id = create_workflow(syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-republish")[
            0
        ]

        syntara_api.workflows.publish_version(
            workflow_id=wf_id, version=1, body=PublishVersionRequest()
        ).assert_and_get()

        syntara_api.workflows.update(
            workflow_id=wf_id,
            body=WorkflowUpdate(workflow_definition=_simple_definition(activity_id="task2", description="v2")),
        ).assert_and_get()

        syntara_api.workflows.publish_version(
            workflow_id=wf_id, version=2, body=PublishVersionRequest()
        ).assert_and_get()

        republish_resp = syntara_api.workflows.publish_version(
            workflow_id=wf_id, version=1, body=PublishVersionRequest()
        )
        assert republish_resp.status_code == HTTPStatus.OK

        versions_resp = syntara_api.workflows.list_versions(workflow_id=wf_id)
        assert versions_resp.parsed is not None
        by_ver = {v.version: v for v in versions_resp.parsed.resources}
        assert by_ver[1].status == "published"
        assert by_ver[2].status == "previously_published"

        wf_resp = syntara_api.workflows.get(workflow_id=wf_id)
        assert wf_resp.parsed is not None
        assert wf_resp.parsed.published_version_id is not None

    def test_idempotent_republish_updates_metadata(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-5: Re-publishing the same version updates name and change_description."""
        wf_id = create_workflow(
            syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-idempotent"
        )[0]

        syntara_api.workflows.publish_version(
            workflow_id=wf_id,
            version=1,
            body=PublishVersionRequest.from_dict({"name": "original", "change_description": "first publish"}),
        ).assert_and_get()

        republish_resp = syntara_api.workflows.publish_version(
            workflow_id=wf_id,
            version=1,
            body=PublishVersionRequest.from_dict({"name": "updated", "change_description": "metadata update"}),
        )
        assert republish_resp.status_code == HTTPStatus.OK
        assert republish_resp.parsed is not None
        assert republish_resp.parsed.version is not None
        assert republish_resp.parsed.version.name == "updated"
        assert republish_resp.parsed.version.change_description == "metadata update"
        assert republish_resp.parsed.version.status == "published"

    def test_unpublish_workflow(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-6: Unpublish sets published_version_id to null and is_enabled to false."""
        wf_id = create_workflow(syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-unpublish")[
            0
        ]

        syntara_api.workflows.publish_version(
            workflow_id=wf_id, version=1, body=PublishVersionRequest()
        ).assert_and_get()

        unpublish_resp = syntara_api.workflows.unpublish(workflow_id=wf_id)
        assert unpublish_resp.status_code == HTTPStatus.OK
        assert unpublish_resp.parsed is not None
        assert unpublish_resp.parsed.published_version_id is None
        assert unpublish_resp.parsed.is_enabled is False

        versions_resp = syntara_api.workflows.list_versions(workflow_id=wf_id)
        assert versions_resp.parsed is not None
        assert versions_resp.parsed.resources[0].status == "previously_published"

    def test_unpublish_when_not_published_returns_400(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-7: Unpublishing a workflow that is not published returns 400."""
        wf_id = create_workflow(syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-unpub-400")[
            0
        ]

        resp = syntara_api.workflows.unpublish(workflow_id=wf_id)
        assert resp.status_code == HTTPStatus.BAD_REQUEST

    def test_publish_nonexistent_version_returns_404(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-8: Publishing a version that doesn't exist returns 404."""
        wf_id = create_workflow(syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-pub-404")[0]

        resp = syntara_api.workflows.publish_version(workflow_id=wf_id, version=999, body=PublishVersionRequest())
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestExecutionRouting:
    """E2E tests for execution version routing (API-11)."""

    def test_manual_run_on_unpublished_workflow(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-11: Manual execution on an unpublished workflow uses current version."""
        wf_id = create_workflow(
            syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-manual-run"
        )[0]

        wf_resp = syntara_api.workflows.get(workflow_id=wf_id)
        assert wf_resp.parsed is not None
        assert wf_resp.parsed.published_version_id is None

        exec_resp = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=wf_id, trigger_node_id="trigger"),
        )
        assert exec_resp.status_code == HTTPStatus.CREATED
        assert exec_resp.parsed is not None
        assert exec_resp.parsed.id is not None


class TestRestoreEdgeCases:
    """E2E tests for restore edge cases (API-13, API-14)."""

    def test_restore_current_version_is_noop(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-13: Restoring the current (latest) version creates no new version."""
        wf_id = create_workflow(
            syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-restore-noop"
        )[0]

        restore_resp = syntara_api.workflows.restore_version(workflow_id=wf_id, version=1)
        assert restore_resp.status_code == HTTPStatus.OK
        assert restore_resp.parsed is not None
        assert restore_resp.parsed.current_version == 1

        versions_resp = syntara_api.workflows.list_versions(workflow_id=wf_id)
        assert versions_resp.parsed is not None
        assert len(versions_resp.parsed.resources) == 1

    def test_restore_nonexistent_version_returns_404(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-14: Restoring a version that doesn't exist returns 404."""
        wf_id = create_workflow(
            syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-restore-404"
        )[0]

        resp = syntara_api.workflows.restore_version(workflow_id=wf_id, version=999)
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestExportEdgeCases:
    """E2E tests for export edge cases (API-16)."""

    def test_export_nonexistent_version_returns_404(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-16: Exporting a version that doesn't exist returns 404."""
        wf_id = create_workflow(
            syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-export-404"
        )[0]

        resp = syntara_api.workflows.export_version(workflow_id=wf_id, version=999)
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestVersionNameEdgeCases:
    """E2E tests for version name edge cases (API-17)."""

    def test_publish_with_empty_name(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-17: Empty string name is accepted (version name is optional, UI shows date instead)."""
        wf_id = create_workflow(
            syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-name-empty"
        )[0]

        resp = syntara_api.workflows.publish_version(
            workflow_id=wf_id, version=1, body=PublishVersionRequest.from_dict({"name": ""})
        )
        assert resp.status_code == HTTPStatus.OK
        assert resp.parsed is not None
        assert resp.parsed.version is not None
        assert resp.parsed.version.name == ""

    def test_publish_with_max_length_name(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-17: Name at max length (255 characters) is accepted."""
        wf_id = create_workflow(syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-name-long")[
            0
        ]
        long_name = "A" * 255

        resp = syntara_api.workflows.publish_version(
            workflow_id=wf_id, version=1, body=PublishVersionRequest.from_dict({"name": long_name})
        )
        assert resp.status_code == HTTPStatus.OK
        assert resp.parsed is not None
        assert resp.parsed.version is not None
        assert resp.parsed.version.name == long_name

    def test_publish_with_special_characters(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-17: Backend stores names verbatim; frontend escapes on render (React auto-escapes)."""
        wf_id = create_workflow(
            syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-name-special"
        )[0]
        special_name = "Release \U0001f680 v2.0 — <script>alert('xss')</script> café"

        resp = syntara_api.workflows.publish_version(
            workflow_id=wf_id, version=1, body=PublishVersionRequest.from_dict({"name": special_name})
        )
        assert resp.status_code == HTTPStatus.OK
        assert resp.parsed is not None
        assert resp.parsed.version is not None
        assert resp.parsed.version.name == special_name


class TestConflictDetection:
    """E2E tests for optimistic concurrency conflict detection (API-19)."""

    def test_stale_save_returns_409(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-19: Saving with a stale expected_version returns 409 Conflict."""
        wf_id = create_workflow(
            syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-conflict-409"
        )[0]

        syntara_api.workflows.update(
            workflow_id=wf_id,
            body=WorkflowUpdate(
                workflow_definition=_simple_definition(activity_id="task2", description="v2"),
            ),
        ).assert_and_get()

        resp = syntara_api.workflows.update(
            workflow_id=wf_id,
            body=WorkflowUpdate(
                workflow_definition=_simple_definition(activity_id="task3", description="v3"),
                expected_version=1,
            ),
        )
        assert resp.status_code == HTTPStatus.CONFLICT

    def test_correct_expected_version_succeeds(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-19: Saving with the correct expected_version succeeds."""
        wf_id = create_workflow(
            syntara_api, first_project_id, definition=_simple_definition(), prefix="e2e-conflict-ok"
        )[0]

        resp = syntara_api.workflows.update(
            workflow_id=wf_id,
            body=WorkflowUpdate(
                workflow_definition=_simple_definition(activity_id="task2", description="v2"),
                expected_version=1,
            ),
        )
        assert resp.status_code == HTTPStatus.OK
        assert resp.parsed is not None
        assert resp.parsed.current_version == 2


def _wait_definition(activity_id: str = "wait_step", wait_seconds: int = 3) -> WorkflowDefinition:
    """Create a workflow definition with a wait node for in-flight testing."""
    return WorkflowDefinition.from_dict(
        {
            "schema_version": "2.0.0",
            "name": "e2e-inflight",
            "description": "in-flight test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": activity_id,
                    "name": activity_id,
                    "type": "wait",
                    "parameters": {"duration": wait_seconds},
                },
            ],
            "edges": [{"from": "trigger", "to": activity_id}],
        }
    )


class TestInFlightExecution:
    """E2E test for in-flight execution version binding (API-23)."""

    def test_inflight_execution_continues_on_original_version(
        self, syntara_api: SyntaraApiRegistry, create_workflow: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """API-23: Publishing a new version does not affect an in-flight execution.

        1. Create workflow with a wait node (3s)
        2. Start execution on v1
        3. While running, publish v1 and create v2 with different definition
        4. Wait for execution to complete
        5. Verify it completed with v1's definition (wait node, not script node)
        """
        wf_id = create_workflow(
            syntara_api,
            first_project_id,
            prefix="e2e-inflight",
            definition=_wait_definition(activity_id="wait_v1", wait_seconds=3),
        )[0]

        exec_resp = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=wf_id, trigger_node_id="trigger"),
        )
        assert exec_resp.status_code == HTTPStatus.CREATED
        assert exec_resp.parsed is not None
        exec_id = str(exec_resp.parsed.id)

        syntara_api.workflows.update(
            workflow_id=wf_id,
            body=WorkflowUpdate(
                workflow_definition=_simple_definition(activity_id="script_v2", description="v2"),
            ),
        ).assert_and_get()
        syntara_api.workflows.publish_version(
            workflow_id=wf_id, version=2, body=PublishVersionRequest()
        ).assert_and_get()

        result = poll_execution(syntara_api, exec_id, timeout=30)
        assert result.status == ExecutionStatus.COMPLETED

        activities = {a.activity_id: a.status for a in (result.activities or [])}
        assert "wait_v1" in activities, f"Expected wait_v1 activity from v1, got: {list(activities.keys())}"
        assert activities["wait_v1"] == "completed"
