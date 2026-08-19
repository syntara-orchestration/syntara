"""Unit tests for WorkflowService credential:use permission checks.

Covers _check_credential_use_permission and _validate_credential_project_scope:
  - opa_client is None → AuthorizationDeniedError
  - no new credentials → early return (no OPA call)
  - new credential, OPA allowed → no error
  - new credential, OPA denied → AuthorizationDeniedError
  - no credential IDs → early return from _validate_credential_project_scope
  - missing / wrong-project credentials → SafeValueError
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.core.exceptions import SafeValueError
from syntara.workflows.services.workflow_service import WorkflowService


def _make_service(
    *,
    with_opa: bool = True,
    project_name: str = "test-project",
) -> tuple[WorkflowService, AsyncMock]:
    """Build a WorkflowService with mocked session, user, and optional opa_client.

    Returns the service and the raw session mock so callers can reconfigure
    exec() return values without going through the typed svc.session attribute.
    """
    session: AsyncMock = AsyncMock()
    proj_result = MagicMock()
    proj_result.first.return_value = project_name
    session.exec.return_value = proj_result

    user = MagicMock()
    user.id = uuid4()
    user.labels = {}
    user.authz_metadata = {}

    svc = WorkflowService.__new__(WorkflowService)
    svc.session = session
    svc.user = user
    svc.opa_client = MagicMock(spec=AuthzEvaluator) if with_opa else None
    return svc, session


class TestCheckCredentialUsePermission:  # noqa: D101
    @pytest.mark.asyncio
    async def test_no_opa_client_raises(self) -> None:
        svc, _ = _make_service(with_opa=False)
        cred_ids = {str(uuid4())}
        project_id = uuid4()
        with pytest.raises(AuthorizationDeniedError):
            await svc._check_credential_use_permission(cred_ids, previous_credential_ids=None, project_id=project_id)

    @pytest.mark.asyncio
    async def test_no_new_credentials_skips_opa(self) -> None:
        """All credentials already present in previous version — no OPA call."""
        cred_id = str(uuid4())
        project_id = uuid4()
        svc, _ = _make_service()

        with patch("syntara.workflows.services.workflow_service.authorize") as mock_authorize:
            await svc._check_credential_use_permission(
                {cred_id}, previous_credential_ids={cred_id}, project_id=project_id
            )
        mock_authorize.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_credential_allowed_no_error(self) -> None:
        svc, _ = _make_service()
        allowed = MagicMock()
        allowed.allowed = True
        cred_ids = {str(uuid4())}
        project_id = uuid4()

        with patch("syntara.workflows.services.workflow_service.authorize", return_value=allowed):
            await svc._check_credential_use_permission(cred_ids, previous_credential_ids=None, project_id=project_id)

    @pytest.mark.asyncio
    async def test_new_credential_denied_raises(self) -> None:
        svc, _ = _make_service()
        denied = MagicMock()
        denied.allowed = False
        cred_ids = {str(uuid4())}
        project_id = uuid4()

        with patch("syntara.workflows.services.workflow_service.authorize", return_value=denied):
            with pytest.raises(AuthorizationDeniedError):
                await svc._check_credential_use_permission(
                    cred_ids, previous_credential_ids=None, project_id=project_id
                )

    @pytest.mark.asyncio
    async def test_previously_none_treats_all_as_new(self) -> None:
        """previous_credential_ids=None means first save — all credentials are new."""
        svc, _ = _make_service()
        denied = MagicMock()
        denied.allowed = False
        cred_ids = {str(uuid4()), str(uuid4())}
        project_id = uuid4()

        with patch("syntara.workflows.services.workflow_service.authorize", return_value=denied):
            with pytest.raises(AuthorizationDeniedError):
                await svc._check_credential_use_permission(
                    cred_ids, previous_credential_ids=None, project_id=project_id
                )


class TestValidateCredentialProjectScope:  # noqa: D101
    @staticmethod
    def _def_with_cred(cred_id: str) -> dict[str, object]:
        return {
            "schema_version": "2.0.0",
            "nodes": [{"id": "n1", "type": "http_request", "parameters": {"credential_id": cred_id}}],
            "edges": [],
            "triggers": [],
        }

    @pytest.mark.asyncio
    async def test_no_credentials_returns_early(self) -> None:
        svc, _ = _make_service()
        empty_def = {"schema_version": "2.0.0", "nodes": [], "edges": [], "triggers": []}
        await svc._validate_credential_project_scope(empty_def, project_id=uuid4())

    @pytest.mark.asyncio
    async def test_missing_credential_raises(self) -> None:
        cred_id = str(uuid4())
        project_id = uuid4()
        svc, session = _make_service()

        missing_result = MagicMock()
        missing_result.all.return_value = []
        session.exec.return_value = missing_result

        definition = self._def_with_cred(cred_id)
        with pytest.raises(SafeValueError):
            await svc._validate_credential_project_scope(definition, project_id=project_id)

    @pytest.mark.asyncio
    async def test_credential_in_wrong_project_raises(self) -> None:
        cred_id = uuid4()
        project_id = uuid4()
        other_project_id = uuid4()
        svc, session = _make_service()

        wrong_proj_result = MagicMock()
        wrong_proj_result.all.return_value = [(cred_id, other_project_id)]
        session.exec.return_value = wrong_proj_result

        definition = self._def_with_cred(str(cred_id))
        with pytest.raises(SafeValueError):
            await svc._validate_credential_project_scope(definition, project_id=project_id)

    @pytest.mark.asyncio
    async def test_valid_credential_calls_use_permission_check(self) -> None:
        """Valid credential in correct project proceeds to credential:use check."""
        cred_id = uuid4()
        project_id = uuid4()
        svc, session = _make_service()

        valid_result = MagicMock()
        valid_result.all.return_value = [(cred_id, project_id)]
        session.exec.return_value = valid_result

        allowed = MagicMock()
        allowed.allowed = True
        with patch("syntara.workflows.services.workflow_service.authorize", return_value=allowed):
            await svc._validate_credential_project_scope(self._def_with_cred(str(cred_id)), project_id=project_id)


class TestPublishWorkflowVersionCredentialCheck:  # noqa: D101
    @pytest.mark.asyncio
    async def test_inline_definition_triggers_credential_scope_check(self) -> None:
        """publish_workflow_version with inline_definition calls _validate_credential_project_scope.

        Covers lines 1077-1082: previous_cred_ids assignment and the validation call
        in the workflow_definition-is-not-None branch of publish_workflow_version.
        """
        svc, _ = _make_service()

        workflow_id = uuid4()
        project_id = uuid4()

        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.is_builtin = False
        mock_workflow.project_id = project_id
        mock_workflow.published_version = None

        # Previous version has an existing workflow_definition (triggers previous_cred_ids extraction)
        mock_version = MagicMock()
        mock_version.version = 1
        mock_version.workflow_definition = {"nodes": [], "edges": [], "triggers": []}

        inline_def = {
            "schema_version": "2.0.0",
            "nodes": [{"id": "n1", "type": "http_request", "parameters": {}}],
            "edges": [],
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        }

        # Mock validator to return clean result (no errors/warnings)
        mock_validator_result = MagicMock()
        mock_validator_result.error_count = 0
        mock_validator_result.warning_count = 0
        mock_validator_result.findings = []
        mock_validator = MagicMock()
        mock_validator.collect_findings.return_value = mock_validator_result

        # Sentinel: _validate_credential_project_scope is called → stop there
        sentinel = RuntimeError("credential scope check invoked")

        with (
            patch.object(svc, "_get_workflow_for_update", return_value=mock_workflow),
            patch.object(svc, "_check_expected_version"),
            patch.object(svc, "_get_version_or_none", return_value=mock_version),
            patch("syntara.workflows.services.workflow_service.workflow_validator", mock_validator),
            patch.object(svc, "_validate_credential_project_scope", side_effect=sentinel),
            pytest.raises(RuntimeError, match="credential scope check invoked"),
        ):
            await svc.publish_workflow_version(workflow_id, version=1, workflow_definition=inline_def)


class TestValidateNoSecretUrlConflicts:  # noqa: D101
    @staticmethod
    def _def_with_http_node(
        *, url: str | None = None, credential_id: str | None = None, node_name: str = "my-http-node"
    ) -> dict[str, object]:
        params: dict[str, object] = {"method": "GET"}
        if url is not None:
            params["url"] = url
        if credential_id is not None:
            params["credential_id"] = credential_id
        return {
            "schema_version": "2.0.0",
            "nodes": [{"id": "n1", "type": "http_request", "name": node_name, "parameters": params}],
            "edges": [],
            "triggers": [],
        }

    @pytest.mark.asyncio
    async def test_no_http_nodes_returns_early(self) -> None:
        svc, _ = _make_service()
        definition: dict[str, object] = {
            "schema_version": "2.0.0",
            "nodes": [{"id": "n1", "type": "agentic", "parameters": {}}],
            "edges": [],
            "triggers": [],
        }
        await svc._validate_no_secret_url_conflicts(definition)

    @pytest.mark.asyncio
    async def test_http_node_with_url_only_no_error(self) -> None:
        svc, _ = _make_service()
        definition = self._def_with_http_node(url="https://example.com/api")
        await svc._validate_no_secret_url_conflicts(definition)

    @pytest.mark.asyncio
    async def test_http_node_with_credential_only_no_error(self) -> None:
        svc, _ = _make_service()
        definition = self._def_with_http_node(credential_id=str(uuid4()))
        await svc._validate_no_secret_url_conflicts(definition)

    @pytest.mark.asyncio
    async def test_secret_url_credential_with_explicit_url_raises(self) -> None:
        cred_id = uuid4()
        svc, session = _make_service()

        db_result = MagicMock()
        db_result.all.return_value = [(cred_id, {"extra_vars": {"auth_type": "url", "secret_url": "{{url}}"}})]
        session.exec.return_value = db_result

        definition = self._def_with_http_node(
            url="https://example.com/api", credential_id=str(cred_id), node_name="Send webhook"
        )
        with pytest.raises(SafeValueError, match="Send webhook"):
            await svc._validate_no_secret_url_conflicts(definition)

    @pytest.mark.asyncio
    async def test_non_url_credential_with_explicit_url_no_error(self) -> None:
        cred_id = uuid4()
        svc, session = _make_service()

        db_result = MagicMock()
        db_result.all.return_value = [(cred_id, {"extra_vars": {"auth_type": "bearer", "bearer_token": "{{token}}"}})]
        session.exec.return_value = db_result

        definition = self._def_with_http_node(url="https://example.com/api", credential_id=str(cred_id))
        await svc._validate_no_secret_url_conflicts(definition)

    @pytest.mark.asyncio
    async def test_multiple_nodes_only_conflicting_one_raises(self) -> None:
        clean_cred, bad_cred = uuid4(), uuid4()
        svc, session = _make_service()

        db_result = MagicMock()
        db_result.all.return_value = [
            (clean_cred, {"extra_vars": {"auth_type": "bearer"}}),
            (bad_cred, {"extra_vars": {"auth_type": "url", "secret_url": "{{url}}"}}),
        ]
        session.exec.return_value = db_result

        definition: dict[str, object] = {
            "schema_version": "2.0.0",
            "nodes": [
                {
                    "id": "n1",
                    "type": "http_request",
                    "name": "API call",
                    "parameters": {
                        "method": "GET",
                        "url": "https://api.example.com",
                        "credential_id": str(clean_cred),
                    },
                },
                {
                    "id": "n2",
                    "type": "http_request",
                    "name": "Slack hook",
                    "parameters": {
                        "method": "POST",
                        "url": "https://slack.com/hook",
                        "credential_id": str(bad_cred),
                    },
                },
            ],
            "edges": [],
            "triggers": [],
        }
        with pytest.raises(SafeValueError, match="Slack hook"):
            await svc._validate_no_secret_url_conflicts(definition)
