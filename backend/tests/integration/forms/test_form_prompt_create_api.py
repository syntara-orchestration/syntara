"""Integration tests for form_prompt creation API endpoint.

Tests verify that form_prompts are correctly created through the internal
Forms API endpoint.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.forms.models.form_fields import DropdownField, ResolvedOptions
from syntara.forms.models.form_prompt import FormPrompt
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.execution import Execution, ExecutionStatus

FORM_PROMPTS_URL = "/api/v1/form_prompts"

# Minimal valid form definition for integration tests
_MINIMAL_FORM_DEFINITION = {
    "fields": [{"value_name": "field1", "type": "text", "label": "Test Field", "required": False}]
}


def _form_prompt_payload(
    execution_id: UUID,
    project_id: UUID,
    prompt_node_id: str = "form1",
    name: str = "Test Form",
    form_definition: dict[str, Any] | None = None,
    loop_iteration_path: list[int] | None = None,
) -> dict[str, object]:
    """Build a minimal form_prompt creation request payload."""
    iteration_path = loop_iteration_path or []
    # Build temporal_activity_id from prompt_node_id and loop_iteration_path
    temporal_activity_id = prompt_node_id
    if iteration_path:
        temporal_activity_id += "".join(f"_iter_{i}" for i in iteration_path)

    return {
        "execution_id": str(execution_id),
        "project_id": str(project_id),
        "prompt_node_id": prompt_node_id,
        "name": name,
        "form_definition": form_definition or _MINIMAL_FORM_DEFINITION,
        "loop_iteration_path": iteration_path,
        "temporal_activity_id": temporal_activity_id,
    }


async def _create_execution_for_workflow(
    session: AsyncSession,
    user: User,
    project_id: UUID,
    workflow_name: str,
    workflow_definition: dict[str, Any],
) -> Execution:
    """Create a published workflow named ``workflow_name`` with a single execution.

    Used by the workflow_name sort tests, which need prompts whose parent
    workflows have known, differing names. Workflow names are unique per
    project (uq_workflows_name_project), so callers must pass distinct names.
    """
    workflow = Workflow(
        name=workflow_name,
        description="Workflow for form prompt sort tests",
        created_by=user.id,
        is_enabled=False,
        current_version=1,
        project_id=project_id,
    )
    session.add(workflow)

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=workflow_definition,
        created_by=user.id,
    )
    session.add(version)
    await session.flush()

    # ck_workflows_is_enabled_published_version_id requires these to agree.
    workflow.published_version_id = version.id
    workflow.is_enabled = True

    execution = Execution(
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        temporal_workflow_id=f"exec-{uuid4()}",
        status=ExecutionStatus.PENDING,
        input_data={},
        created_by=user.id,
        project_id=project_id,
    )
    session.add(execution)
    await session.commit()
    return execution


@pytest.mark.integration
@pytest.mark.asyncio
class TestFormPromptCreateAPI:
    """API integration tests for form_prompt creation."""

    async def test_create_form_prompt_success(self, jwt_client: AsyncClient, test_execution: Execution) -> None:
        """Create form_prompt returns 201 with prompt ID."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id)

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["execution_id"] == str(exec_id)
        assert data["prompt_node_id"] == "form1"
        assert data["status"] == "pending"

    async def test_create_form_prompt_with_responders(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
        test_user: User,
    ) -> None:
        """Create form_prompt with responder_user_ids stores responders."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id)
        payload["responder_user_ids"] = [str(test_user.id)]

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["execution_id"] == str(exec_id)

    async def test_create_form_prompt_with_message(self, jwt_client: AsyncClient, test_execution: Execution) -> None:
        """Create form_prompt with message field succeeds (message not in summary response)."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id)
        payload["message"] = "Please fill out this form carefully"

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        # FormPromptSummary doesn't include message (only 8 minimal fields)
        assert "id" in data
        assert data["execution_id"] == str(exec_id)

    async def test_create_form_prompt_with_resolved_typed_options_round_trips(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        """Resolved typed options are accepted and persist with their original types."""
        form_definition = {
            "fields": [
                {
                    "value_name": "region_id",
                    "type": "dropdown",
                    "label": "Region",
                    "options": {"source": "dynamic_resolved", "values": [{"display_label": "US", "value": 1}]},
                }
            ]
        }
        payload = _form_prompt_payload(
            test_execution.id,
            test_execution.project_id,
            form_definition=form_definition,
        )

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 201
        prompt = await test_db_session.get(FormPrompt, UUID(response.json()["id"]))
        assert prompt is not None
        resolved_field = prompt.form_definition.fields[0]
        assert isinstance(resolved_field, DropdownField)
        assert isinstance(resolved_field.options, ResolvedOptions)
        assert resolved_field.options.source == "dynamic_resolved"
        assert resolved_field.options.values[0].value == 1
        assert type(resolved_field.options.values[0].value) is int

    async def test_create_rejects_typed_static_option_value(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
    ) -> None:
        payload = _form_prompt_payload(
            test_execution.id,
            test_execution.project_id,
            form_definition={
                "fields": [
                    {
                        "value_name": "region_id",
                        "type": "dropdown",
                        "label": "Region",
                        "options": {"source": "static", "values": [{"display_label": "US", "value": 1}]},
                    }
                ]
            },
        )

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 422

    async def test_create_rejects_empty_resolved_options(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
    ) -> None:
        payload = _form_prompt_payload(
            test_execution.id,
            test_execution.project_id,
            form_definition={
                "fields": [
                    {
                        "value_name": "region_id",
                        "type": "dropdown",
                        "label": "Region",
                        "options": {"source": "dynamic_resolved", "values": []},
                    }
                ]
            },
        )

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 422

    async def test_create_duplicate_form_prompt_returns_409(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
    ) -> None:
        """Creating duplicate form_prompt (same execution_id, prompt_node_id, loop_iteration_path) returns 409."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id, prompt_node_id="form1")

        # First request succeeds
        response1 = await jwt_client.post(FORM_PROMPTS_URL, json=payload)
        assert response1.status_code == 201

        # Second request with same keys should fail
        response2 = await jwt_client.post(FORM_PROMPTS_URL, json=payload)
        assert response2.status_code == 409

    async def test_list_form_prompts_by_execution(self, jwt_client: AsyncClient, test_execution: Execution) -> None:
        """List form_prompts filtered by execution_id returns matching prompts."""
        exec_id = test_execution.id

        # Create two form_prompts for same execution
        payload1 = _form_prompt_payload(exec_id, test_execution.project_id, prompt_node_id="form1", name="Form 1")
        payload2 = _form_prompt_payload(exec_id, test_execution.project_id, prompt_node_id="form2", name="Form 2")

        response1 = await jwt_client.post(FORM_PROMPTS_URL, json=payload1)
        response2 = await jwt_client.post(FORM_PROMPTS_URL, json=payload2)
        assert response1.status_code == 201
        assert response2.status_code == 201

        # List by execution
        list_response = await jwt_client.get(FORM_PROMPTS_URL, params={"execution_id": str(exec_id)})
        assert list_response.status_code == 200

        data = list_response.json()
        assert "resources" in data
        assert len(data["resources"]) == 2

        prompt_names = {p["name"] for p in data["resources"]}
        assert "Form 1" in prompt_names
        assert "Form 2" in prompt_names

        for item in data["resources"]:
            assert "created_at" in item
            assert "workflow_name" in item
            assert "responded_at" in item
            assert "timeout_at" in item
            assert "temporal_activity_id" not in item
            assert "loop_iteration_path" not in item

    async def test_list_form_prompts_sort_by_workflow_name(
        self, jwt_client: AsyncClient, test_execution: Execution
    ) -> None:
        """Sort by workflow_name is accepted and returns 200 (join sort on workflow)."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id, name="Sort by workflow test")
        create_response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)
        assert create_response.status_code == 201

        for sort_param in ("workflow_name", "-workflow_name"):
            list_response = await jwt_client.get(FORM_PROMPTS_URL, params={"sort": sort_param})
            assert list_response.status_code == 200, list_response.text
            data = list_response.json()
            assert "resources" in data

    async def test_list_form_prompts_sort_by_workflow_name_orders_results(
        self,
        jwt_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_execution: Execution,
        test_workflow_definition: dict[str, Any],
    ) -> None:
        """Sorting by workflow_name orders prompts by their parent workflow's name."""
        project_id = test_execution.project_id
        suffix = uuid4().hex[:8]
        # Created out of alphabetical order so a pass cannot be an artifact of insertion order.
        workflow_names = [f"zulu-{suffix}", f"alpha-{suffix}", f"mike-{suffix}"]

        created_ids: set[str] = set()
        for workflow_name in workflow_names:
            execution = await _create_execution_for_workflow(
                test_db_session, test_user, project_id, workflow_name, test_workflow_definition
            )
            create_response = await jwt_client.post(
                FORM_PROMPTS_URL,
                json=_form_prompt_payload(execution.id, project_id, name=f"prompt-{workflow_name}"),
            )
            assert create_response.status_code == 201, create_response.text
            created_ids.add(create_response.json()["id"])

        ascending = sorted(workflow_names)
        for sort_param, expected in (
            ("workflow_name", ascending),
            ("-workflow_name", list(reversed(ascending))),
        ):
            list_response = await jwt_client.get(
                FORM_PROMPTS_URL,
                params={"sort": sort_param, "project_id": str(project_id), "limit": "50"},
            )
            assert list_response.status_code == 200, list_response.text
            observed = [
                item["workflow_name"] for item in list_response.json()["resources"] if item["id"] in created_ids
            ]
            assert observed == expected, f"sort={sort_param}"

    async def test_list_form_prompts_sort_by_workflow_name_tie_breaks_on_id(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
    ) -> None:
        """Prompts sharing a workflow name fall back to the id tiebreaker.

        All prompts hang off a single execution, so every row has an identical
        workflow_name and ordering is decided entirely by the id tiebreaker that
        BaseService appends to the sort.
        """
        exec_id = test_execution.id
        created_ids: list[str] = []
        for index in range(3):
            create_response = await jwt_client.post(
                FORM_PROMPTS_URL,
                json=_form_prompt_payload(
                    exec_id,
                    test_execution.project_id,
                    prompt_node_id=f"tied{index}",
                    name=f"Tied form {index}",
                ),
            )
            assert create_response.status_code == 201, create_response.text
            created_ids.append(create_response.json()["id"])

        # Postgres orders uuid bytewise, matching UUID comparison in Python.
        ascending = sorted(created_ids, key=UUID)
        for sort_param, expected in (
            ("workflow_name", ascending),
            ("-workflow_name", list(reversed(ascending))),
        ):
            list_response = await jwt_client.get(
                FORM_PROMPTS_URL,
                params={"sort": sort_param, "execution_id": str(exec_id), "limit": "50"},
            )
            assert list_response.status_code == 200, list_response.text
            resources = list_response.json()["resources"]
            assert len({item["workflow_name"] for item in resources}) == 1, "expected a single tied workflow name"
            assert [item["id"] for item in resources] == expected, f"sort={sort_param}"

    async def test_list_form_prompts_sort_by_workflow_name_paginates_forward_and_back(
        self,
        jwt_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_execution: Execution,
        test_workflow_definition: dict[str, Any],
    ) -> None:
        """Cursor pagination over a workflow_name sort is stable in both directions."""
        project_id = test_execution.project_id
        suffix = uuid4().hex[:8]
        workflow_names = [f"{letter}-{suffix}" for letter in ("charlie", "alpha", "echo", "bravo", "delta")]

        for workflow_name in workflow_names:
            execution = await _create_execution_for_workflow(
                test_db_session, test_user, project_id, workflow_name, test_workflow_definition
            )
            create_response = await jwt_client.post(
                FORM_PROMPTS_URL,
                json=_form_prompt_payload(execution.id, project_id, name=f"prompt-{workflow_name}"),
            )
            assert create_response.status_code == 201, create_response.text

        base_params = {"sort": "workflow_name", "project_id": str(project_id), "limit": "2"}

        # Walk forward, collecting one list of names per page.
        forward_pages: list[list[str]] = []
        cursor: str | None = None
        for _ in range(10):  # bound guards against a cursor that never terminates
            params = dict(base_params)
            if cursor:
                params["cursor"] = cursor
            response = await jwt_client.get(FORM_PROMPTS_URL, params=params)
            assert response.status_code == 200, response.text
            data = response.json()
            forward_pages.append([item["workflow_name"] for item in data["resources"]])
            cursor = data["next"]
            if not cursor:
                break
        else:
            pytest.fail("forward pagination did not terminate")

        assert all(len(page) <= 2 for page in forward_pages)
        # Pages concatenate to the full ordered set: nothing skipped, nothing repeated.
        assert [name for page in forward_pages for name in page] == sorted(workflow_names)

        # Walk back from the final page; pages should replay in reverse.
        backward_pages: list[list[str]] = []
        cursor = data["prev"]
        for _ in range(10):
            if not cursor:
                break
            params = dict(base_params)
            params["cursor"] = cursor
            response = await jwt_client.get(FORM_PROMPTS_URL, params=params)
            assert response.status_code == 200, response.text
            data = response.json()
            backward_pages.append([item["workflow_name"] for item in data["resources"]])
            cursor = data["prev"]
        else:
            pytest.fail("backward pagination did not terminate")

        assert backward_pages == list(reversed(forward_pages[:-1]))

    async def test_list_form_prompts_includes_submission_metadata(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
        test_user: User,
    ) -> None:
        """List returns responded_at and responded_by after a prompt is submitted."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id, name="Responded form")
        create_response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)
        assert create_response.status_code == 201
        prompt_id = create_response.json()["id"]

        submit_response = await jwt_client.post(
            f"{FORM_PROMPTS_URL}/{prompt_id}/submit",
            json={"response_data": {"field1": "answer"}},
        )
        assert submit_response.status_code == 200

        list_response = await jwt_client.get(FORM_PROMPTS_URL, params={"execution_id": str(exec_id)})
        assert list_response.status_code == 200
        resources = list_response.json()["resources"]
        submitted = next(item for item in resources if item["id"] == prompt_id)
        assert submitted["status"] == "submitted"
        assert submitted["responded_at"] is not None
        assert submitted["responded_by"] is not None
        assert submitted["responded_by"]["name"]

    async def test_batch_update_form_prompt_status(self, jwt_client: AsyncClient, test_execution: Execution) -> None:
        """Batch update form_prompt status via /form_prompts/batch endpoint."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id)

        # Create prompt
        create_response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)
        assert create_response.status_code == 201
        prompt_id = create_response.json()["id"]

        # Batch update to expired
        batch_payload = {"updates": [{"prompt_id": prompt_id, "status": "expired"}]}
        batch_response = await jwt_client.post(f"{FORM_PROMPTS_URL}/batch", json=batch_payload)

        assert batch_response.status_code == 200
        batch_result = batch_response.json()
        assert batch_result["total_success"] == 1
        assert batch_result["total_failed"] == 0

    async def test_create_form_prompt_with_loop_iteration_path(
        self,
        jwt_client: AsyncClient,
        test_execution: Execution,
    ) -> None:
        """Create form_prompt with loop_iteration_path stores the path."""
        exec_id = test_execution.id
        payload = _form_prompt_payload(exec_id, test_execution.project_id, loop_iteration_path=[0, 1])

        response = await jwt_client.post(FORM_PROMPTS_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["loop_iteration_path"] == [0, 1]
        assert data["temporal_activity_id"] == "form1_iter_0_iter_1"
