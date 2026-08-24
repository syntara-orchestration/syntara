"""E2E tests for credential API endpoints.

Covers tests 42, 44-52 from the ANSTRAT-1901 test plan — the API-side
tests that belong in syntara rather than syntara-ui:

- Secret field masking ($encrypted$ sentinel)
- Workflow execution with valid / disabled / deleted credentials
- Credential value scrubbing in execution history
- RBAC enforcement (admin, user, auditor, project-scoped)

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from uuid import UUID

    from orchestrator_test_sdk.factories.credentials import CredentialFactory
    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models.execution_read import ExecutionRead


if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import HTTPBIN_URL, create_and_run_workflow, poll_execution, requires_httpbin
from orchestrator_test_sdk.factories import get_basic_auth_type_id, get_bearer_token_type_id
from syntara_api_client.models.credential_create import CredentialCreate
from syntara_api_client.models.credential_create_inputs import CredentialCreateInputs
from syntara_api_client.models.credential_update import CredentialUpdate
from syntara_api_client.models.credential_update_inputs_type_0 import CredentialUpdateInputsType0
from syntara_api_client.models.execution_create import ExecutionCreate
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.workflow_create import WorkflowCreate
from syntara_api_client.models.workflow_definition import WorkflowDefinition

pytestmark = [pytest.mark.e2e]

ENCRYPTED_SENTINEL = "$encrypted$"

# ===================================================================
# Test 42: Secret Field Security — API Side
# ===================================================================


class TestSecretFieldMasking:
    """Verify the API never returns plaintext secret values."""

    def test_create_response_masks_secrets(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, create_credential: CredentialFactory
    ) -> None:
        """POST /credentials response must contain $encrypted$, not plaintext."""
        _, _, cred, secret = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-secret-mask-create")
        )
        assert cred["inputs"]["token"] == ENCRYPTED_SENTINEL
        assert secret not in str(cred)

    def test_get_response_masks_secrets(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, create_credential: CredentialFactory
    ) -> None:
        """GET /credentials/{id} must contain $encrypted$, not plaintext."""
        cred_id, _, _, secret = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-secret-mask-get")
        )
        credential = syntara_api.credentials.get(credential_id=cred_id).assert_and_get()
        data = credential.to_dict()
        assert data["inputs"]["token"] == ENCRYPTED_SENTINEL
        assert secret not in str(data)

    def test_list_response_masks_secrets(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, create_credential: CredentialFactory
    ) -> None:
        """GET /credentials list must not leak plaintext secrets."""
        _, _, _, secret = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-secret-mask-list")
        )
        credentials_list = syntara_api.credentials.list().assert_and_get()
        raw = str(credentials_list)
        assert secret not in raw

    def test_update_with_sentinel_returns_encrypted(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, create_credential: CredentialFactory
    ) -> None:
        """PATCH with $encrypted$ inputs still returns $encrypted$ on GET."""
        cred_id, *_ = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-secret-mask-update")
        )
        syntara_api.credentials.update(
            credential_id=cred_id,
            body=CredentialUpdate(
                description="updated description",
                inputs=CredentialUpdateInputsType0.from_dict({"token": ENCRYPTED_SENTINEL}),
            ),
        ).assert_and_get()
        credential = syntara_api.credentials.get(credential_id=cred_id).assert_and_get()
        assert credential.to_dict()["inputs"]["token"] == ENCRYPTED_SENTINEL


# ===================================================================
# Test 44: Workflow Execution with Valid Credential
# ===================================================================


def _http_request_workflow(name: str, url: str, credential_id: str, method: str = "GET") -> dict[str, Any]:
    """Build a workflow definition with an http_request node and credential."""
    return {
        "schema_version": "2.0.0",
        "name": name,
        "description": f"E2E credential test: {name}",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "api_call",
                "name": "API Call",
                "type": "http_request",
                "parameters": {
                    "method": method,
                    "url": url,
                    "credential_id": credential_id,
                },
            },
        ],
        "edges": [{"from": "trigger", "to": "api_call"}],
    }


def _get_activity_output(execution: ExecutionRead, activity_id: str) -> dict[str, Any]:
    """Extract the output dict from an activity's output_data."""
    activities = {a.activity_id: a for a in (execution.activities or [])}
    activity = activities[activity_id]
    output_data = activity.output_data
    if output_data is None:
        return {}
    if isinstance(output_data, dict):
        return output_data
    result: dict[str, Any] = getattr(output_data, "additional_properties", {})
    return result


@requires_httpbin
class TestWorkflowWithValidCredential:
    """Verify credential resolution succeeds at runtime (ANSTRAT-1901)."""

    def test_bearer_token_credential_resolves(
        self,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
        create_credential: CredentialFactory,
    ) -> None:
        """HTTP request with Bearer Token credential hits httpbin /bearer — expect 200."""
        cred_id, *_ = create_credential(
            api=syntara_api,
            project_id=first_project_id,
            name=unique_name("e2e-cred-bearer"),
        )

        workflow_name = unique_name("e2e-cred-bearer-test")

        definition = _http_request_workflow(
            name=workflow_name,
            url=f"{HTTPBIN_URL}/bearer",
            credential_id=str(cred_id),
        )
        execution = create_and_run_workflow(
            syntara_api, workflow_name, definition, timeout=30, project_id=first_project_id
        )

        assert execution.status == ExecutionStatus.COMPLETED, f"Unexpected status: {execution.status}"
        output = _get_activity_output(execution, "api_call")
        assert output.get("status_code") == 200
        body = output.get("body", {})
        assert body.get("authenticated") is True

    def test_basic_auth_credential_resolves(
        self,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
        create_credential: CredentialFactory,
    ) -> None:
        """HTTP request with Basic Auth credential hits httpbin /basic-auth — expect 200."""
        cred_id, *_ = create_credential(
            api=syntara_api,
            project_id=first_project_id,
            name=unique_name("e2e-cred-basic"),
            type_id=get_basic_auth_type_id(syntara_api),
            inputs={"username": "admin", "password": "secret123"},
        )

        workflow_name = unique_name("e2e-cred-basic-test")

        definition = _http_request_workflow(
            name=workflow_name,
            url=f"{HTTPBIN_URL}/basic-auth/admin/secret123",
            credential_id=str(cred_id),
        )
        execution = create_and_run_workflow(
            syntara_api, workflow_name, definition, timeout=30, project_id=first_project_id
        )

        if execution.status == ExecutionStatus.FAILED:
            output = _get_activity_output(execution, "api_call")
            if not output.get("status_code"):
                pytest.skip("Backend could not reach httpbin — network connectivity issue in this environment")
        assert execution.status == ExecutionStatus.COMPLETED, f"Unexpected status: {execution.status}"
        output = _get_activity_output(execution, "api_call")
        assert output.get("status_code") == 200
        body = output.get("body", {})
        assert body.get("authenticated") is True
        assert body.get("user") == "admin"

    def test_no_credential_returns_401(
        self,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
    ) -> None:
        """HTTP request to a protected endpoint without credential — expect workflow failure with 401."""
        workflow_name = "e2e-cred-none-test"

        definition = {
            "schema_version": "2.0.0",
            "name": workflow_name,
            "description": "E2E: no credential against protected endpoint",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "api_call",
                    "name": "API Call",
                    "type": "http_request",
                    "parameters": {"method": "GET", "url": f"{HTTPBIN_URL}/bearer"},
                },
            ],
            "edges": [{"from": "trigger", "to": "api_call"}],
        }
        execution = create_and_run_workflow(
            syntara_api, workflow_name, definition, timeout=30, project_id=first_project_id
        )

        assert execution.status == ExecutionStatus.FAILED
        output = _get_activity_output(execution, "api_call")
        if not output.get("status_code"):
            pytest.skip("Backend could not reach httpbin — network connectivity issue in this environment")
        assert output.get("status_code") == 401


# ===================================================================
# Test 45: Workflow Execution with Disabled Credential
# ===================================================================


@requires_httpbin
class TestWorkflowWithDisabledCredential:
    """Verify disabled credentials fail with clear error (ANSTRAT-1901)."""

    def test_disabled_credential_fails_then_recovers(
        self,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
        create_credential: CredentialFactory,
    ) -> None:
        """Disable → fail, re-enable → succeed. Confirms no stale disabled state."""
        cred_id, *_ = create_credential(
            api=syntara_api,
            project_id=first_project_id,
            name=unique_name("e2e-cred-disabled"),
        )

        syntara_api.credentials.update(
            credential_id=cred_id,
            body=CredentialUpdate(enabled=False),
        ).assert_and_get()

        workflow_name = unique_name("e2e-cred-disabled-test")

        definition = _http_request_workflow(
            name=workflow_name,
            url=f"{HTTPBIN_URL}/bearer",
            credential_id=str(cred_id),
        )
        execution = create_and_run_workflow(
            syntara_api, workflow_name, definition, timeout=30, project_id=first_project_id
        )

        assert execution.status == ExecutionStatus.FAILED
        activities = {a.activity_id: a for a in (execution.activities or [])}
        api_activity = activities["api_call"]
        assert api_activity.status == "failed"
        error_str = str(api_activity.to_dict()).lower()
        assert "disabled" in error_str, f"Expected 'disabled' in error details, got: {error_str[:500]}"

        syntara_api.credentials.update(
            credential_id=cred_id,
            body=CredentialUpdate(enabled=True),
        ).assert_and_get()

        execution = create_and_run_workflow(
            syntara_api, workflow_name, definition, timeout=30, project_id=first_project_id
        )

        assert execution.status == ExecutionStatus.COMPLETED, f"Unexpected status after re-enable: {execution.status}"
        output = _get_activity_output(execution, "api_call")
        assert output.get("status_code") == 200


# ===================================================================
# Test 46: Workflow Execution with Deleted Credential
# ===================================================================


@requires_httpbin
class TestWorkflowWithDeletedCredential:
    """Verify deleted credentials fail with clear error (ANSTRAT-1901)."""

    def test_deleted_credential_fails_execution(
        self,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
        create_credential: CredentialFactory,
        cleanup_workflows: list[UUID],
    ) -> None:
        """Delete a credential, execute its workflow — expect failure mentioning 'not found'."""
        cred_id, *_ = create_credential(
            api=syntara_api,
            project_id=first_project_id,
            name=unique_name("e2e-cred-deleted"),
        )

        workflow_name = unique_name("e2e-cred-deleted-test")

        definition = _http_request_workflow(
            name=workflow_name,
            url=f"{HTTPBIN_URL}/bearer",
            credential_id=str(cred_id),
        )
        workflow = syntara_api.workflows.create(
            body=WorkflowCreate(
                name=workflow_name,
                description="E2E: deleted credential test",
                workflow_definition=WorkflowDefinition.from_dict(definition),
                project_id=first_project_id,
            )
        ).assert_and_get()
        cleanup_workflows.append(workflow.id)

        syntara_api.credentials.delete(credential_id=cred_id)

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
        ).assert_and_get()
        execution = poll_execution(syntara_api, str(execution.id), timeout=30)

        assert execution.status == ExecutionStatus.FAILED
        activities = {a.activity_id: a for a in (execution.activities or [])}
        api_activity = activities["api_call"]
        assert api_activity.status == "failed"
        error_str = str(api_activity.to_dict()).lower()
        assert "not found" in error_str, f"Expected 'not found' in error details, got: {error_str[:500]}"


# ===================================================================
# Test 47: Credential Values Not Exposed in Execution History
# ===================================================================


class TestCredentialScrubbing:
    """Verify secret values are scrubbed from execution history (AAP-79021)."""

    _SECRET = "test-e2e-scrub-stdout"  # noqa: S105

    def test_script_stdout_secret_is_scrubbed(
        self,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
        create_credential: CredentialFactory,
    ) -> None:
        """Script node prints credential value to stdout — must be [REDACTED] in execution history."""
        from orchestrator_test_sdk.e2e.helpers import create_and_run_workflow

        cred_id, *_ = create_credential(api=syntara_api, project_id=first_project_id, name="e2e-scrub-stdout")

        workflow_name = unique_name("e2e-scrub-stdout-test")

        definition = {
            "schema_version": "2.0.0",
            "name": workflow_name,
            "description": "AAP-79021: verify value-based credential scrubbing",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "echo_secret",
                    "name": "Echo Secret",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": f'print("{self._SECRET}")',
                        "credential_id": str(cred_id),
                    },
                }
            ],
            "edges": [{"from": "trigger_manual", "to": "echo_secret"}],
        }

        execution = create_and_run_workflow(
            syntara_api, workflow_name, definition, timeout=30, project_id=first_project_id
        )
        status_str = str(execution.status)
        assert status_str in {"completed", "completed_with_errors"}, f"Unexpected status: {status_str}"

        full_response = str(execution.to_dict())
        assert self._SECRET not in full_response, "Plaintext secret leaked into execution response"

        activities = execution.activities or []
        script_activities = [a for a in activities if a.activity_id == "echo_secret"]
        assert len(script_activities) == 1, "Expected exactly one echo_secret activity"

        output = script_activities[0].to_dict().get("output_data") or {}
        output_str = str(output)
        assert self._SECRET not in output_str, "Plaintext secret leaked into activity output_data"
        assert "[REDACTED]" in output_str, "Expected [REDACTED] in scrubbed output_data"


# ===================================================================
# Test 48: RBAC — Admin Full CRUD
# ===================================================================


class TestRbacAdminFullCrud:
    """Admin role has full create, read, update, delete access."""

    def test_admin_crud_lifecycle(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, create_credential: CredentialFactory
    ) -> None:
        """Admin creates, reads, updates, and deletes a credential."""
        cred_id, *_ = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-rbac-admin")
        )

        # Read
        syntara_api.credentials.get(credential_id=cred_id).assert_and_get()

        # Update
        syntara_api.credentials.update(
            credential_id=cred_id,
            body=CredentialUpdate(description="admin updated"),
        ).assert_and_get()

        # Delete
        del_resp = syntara_api.credentials.delete(credential_id=cred_id)
        assert del_resp.status_code == HTTPStatus.NO_CONTENT


# ===================================================================
# Test 49: RBAC — User Cannot Delete
# ===================================================================


class TestRbacUserCannotDelete:
    """User role can create/read/update but NOT delete credentials."""

    def test_user_create_read_update_succeeds(
        self, syntara_api: SyntaraApiRegistry, viewer_api: SyntaraApiRegistry
    ) -> None:
        """User role can create, read, and update credentials."""
        # ANSTRAT-1901: needs user-role client fixture (viewer has no roles)
        # 1. Create credential as user
        # 2. Read it back — assert 200
        # 3. Update description — assert success
        pytest.skip("Requires user-role client fixture (not viewer)")

    def test_user_delete_returns_403(
        self,
        viewer_api: SyntaraApiRegistry,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
        create_credential: CredentialFactory,
    ) -> None:
        """User role attempting DELETE gets 403 Forbidden."""
        cred_id, *_ = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-rbac-user-del")
        )
        resp = viewer_api.credentials.delete(credential_id=cred_id)
        assert resp.status_code == HTTPStatus.FORBIDDEN


# ===================================================================
# Test 50: RBAC — Auditor Read-Only
# ===================================================================


class TestRbacAuditorReadOnly:
    """Auditor role can list and read credentials but cannot mutate."""

    def test_auditor_can_list(self, auditor_api: SyntaraApiRegistry) -> None:
        """Auditor can GET /credentials."""
        resp = auditor_api.credentials.list()
        assert resp.status_code == HTTPStatus.OK

    def test_auditor_can_read(
        self,
        auditor_api: SyntaraApiRegistry,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
        create_credential: CredentialFactory,
    ) -> None:
        """Auditor can GET /credentials/{id}."""
        cred_id, *_ = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-rbac-auditor-read")
        )
        resp = auditor_api.credentials.get(credential_id=cred_id)
        assert resp.status_code == HTTPStatus.OK

    def test_auditor_cannot_create(
        self,
        auditor_api: SyntaraApiRegistry,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
    ) -> None:
        """Auditor POST /credentials gets 403."""
        # Authorization check happens before validation, so we can use valid data
        resp = auditor_api.credentials.create(
            body=CredentialCreate(
                name="should-fail",
                credential_type_id=get_bearer_token_type_id(syntara_api),
                project_id=first_project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "test"}),
            )
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_auditor_cannot_update(
        self,
        auditor_api: SyntaraApiRegistry,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
        create_credential: CredentialFactory,
    ) -> None:
        """Auditor PATCH /credentials/{id} gets 403."""
        cred_id, *_ = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-rbac-auditor-patch")
        )
        resp = auditor_api.credentials.update(
            credential_id=cred_id,
            body=CredentialUpdate(description="nope"),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_auditor_cannot_delete(
        self,
        auditor_api: SyntaraApiRegistry,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
        create_credential: CredentialFactory,
    ) -> None:
        """Auditor DELETE /credentials/{id} gets 403."""
        cred_id, *_ = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-rbac-auditor-del")
        )
        resp = auditor_api.credentials.delete(credential_id=cred_id)
        assert resp.status_code == HTTPStatus.FORBIDDEN


# ===================================================================
# Test 51: RBAC — Project-Scoped Credential Visibility
# ===================================================================


@pytest.mark.skip(reason="TODO: requires two users with different project access")
class TestRbacProjectScopedVisibility:
    """Credentials with project_id are only visible to users with project access."""

    def test_org_level_credential_visible_to_all(self, syntara_api: SyntaraApiRegistry) -> None:
        """Credential with project_id=NULL is visible to all authorized users."""
        # ANSTRAT-1901: implement when workflow+credential wiring is available
        # 1. Create org-level credential (project_id=NULL — if supported)
        # 2. List as user A (with project access) — assert visible
        # 3. List as user B (without project access) — assert visible
        # 4. Cleanup

    def test_project_scoped_credential_hidden_from_unauthorized(self, syntara_api: SyntaraApiRegistry) -> None:
        """Credential scoped to project X is invisible to users without project X access."""
        # ANSTRAT-1901: implement when workflow+credential wiring is available
        # 1. Create project-scoped credential
        # 2. List as user with project access — assert visible
        # 3. List as user without project access — assert NOT visible
        # 4. Direct GET by ID as unauthorized user — assert 403
        # 5. Cleanup


# ===================================================================
# Test 52: RBAC — Permission Denied Error Handling
# ===================================================================


class TestRbacPermissionDeniedResponse:
    """403 responses are well-formed and do not leak internals."""

    def test_403_response_format(
        self,
        auditor_api: SyntaraApiRegistry,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
    ) -> None:
        """403 body follows RFC 9457 problem format without leaking policy names."""
        # Authorization check happens before validation, so we can use valid data
        resp = auditor_api.credentials.create(
            body=CredentialCreate(
                name="forbidden-test",
                credential_type_id=get_bearer_token_type_id(syntara_api),
                project_id=first_project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "test"}),
            )
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

        # Check response body format
        assert resp.content is not None
        body: dict[str, Any] = json.loads(resp.content.decode())
        assert "type" in body or "detail" in body
        raw = str(body).lower()
        assert "policy" not in raw, "403 should not expose internal policy names"
        assert "role_assignment" not in raw, "403 should not expose role details"


# ===================================================================
# project_id immutability (AAP-79246)
# ===================================================================


class TestProjectIdImmutability:
    """Verify project_id cannot be changed after creation."""

    def test_update_credential_rejects_project_id_change(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, create_credential: CredentialFactory
    ) -> None:
        """PATCH with a different project_id must return 422."""
        from syntara_api_client.models.project_create import ProjectCreate

        cred_id, *_ = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-immut-cred")
        )

        other_project = syntara_api.projects.create(
            body=ProjectCreate(
                name=unique_name("e2e-immut-dst-proj"),
                description="Destination project for immutability test",
            )
        ).assert_and_get()

        body = CredentialUpdate(description="attempt project move")
        body["project_id"] = str(other_project.id)
        response = syntara_api.credentials.update(credential_id=cred_id, body=body)
        assert not response.is_success
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_update_credential_accepts_same_project_id(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, create_credential: CredentialFactory
    ) -> None:
        """PATCH with the same project_id must succeed (no-op)."""
        cred_id, *_ = create_credential(
            api=syntara_api, project_id=first_project_id, name=unique_name("e2e-same-proj-cred")
        )

        body = CredentialUpdate(description="same project ok")
        body["project_id"] = str(first_project_id)
        updated = syntara_api.credentials.update(credential_id=cred_id, body=body).assert_and_get()
        assert str(updated.project_id) == str(first_project_id)
