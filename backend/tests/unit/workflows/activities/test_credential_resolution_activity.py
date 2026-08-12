"""Tests for credential resolution Temporal activity (T059)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.credential_resolution_activity import _extract_secret_field_ids


class TestExtractSecretFieldIds:
    """Tests for _extract_secret_field_ids helper."""

    def test_returns_secret_field_ids(self) -> None:
        ct = MagicMock()
        ct.inputs = {
            "fields": [
                {"id": "username", "secret": False},
                {"id": "password", "secret": True},
                {"id": "token", "secret": True},
            ]
        }
        assert _extract_secret_field_ids(ct) == {"password", "token"}

    def test_returns_empty_for_no_secret_fields(self) -> None:
        ct = MagicMock()
        ct.inputs = {"fields": [{"id": "host", "secret": False}]}
        assert _extract_secret_field_ids(ct) == set()

    def test_handles_none_inputs(self) -> None:
        ct = MagicMock()
        ct.inputs = None
        assert _extract_secret_field_ids(ct) == set()

    def test_handles_missing_fields(self) -> None:
        ct = MagicMock()
        ct.inputs = {}
        assert _extract_secret_field_ids(ct) == set()


ACTIVITY_ID = "api-node-1"
CREDENTIAL_ID = str(uuid4())
PROJECT_A_ID = str(uuid4())
PROJECT_B_ID = str(uuid4())


@pytest.fixture
def mock_credential() -> MagicMock:
    """Create a mock credential."""
    cred = MagicMock()
    cred.id = CREDENTIAL_ID
    cred.name = "Test Credential"
    cred.enabled = True
    cred.secret_id = uuid4()
    cred.credential_type_id = uuid4()
    cred.project_id = PROJECT_A_ID
    return cred


@pytest.fixture
def mock_credential_type() -> MagicMock:
    """Create a mock credential type."""
    ct = MagicMock()
    ct.name = "HTTP Bearer Token"
    ct.inputs = {
        "fields": [
            {"id": "token", "label": "Token", "type": "string", "secret": True},
        ],
        "required": ["token"],
    }
    ct.injectors = {
        "extra_vars": {"auth_type": "bearer", "bearer_token": "{{token}}"},
        "env": {},
        "file": {},
    }
    return ct


class TestResolveWorkflowCredentials:
    """Tests for resolve_workflow_credentials activity."""

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_happy_path_resolves_credential(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
        mock_credential: MagicMock,
        mock_credential_type: MagicMock,
    ) -> None:
        """Test successful credential resolution with correct extra_vars."""
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock credential query
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_credential
        mock_session.exec = AsyncMock(return_value=mock_result)

        # Mock credential type fetch
        mock_session.get = AsyncMock(return_value=mock_credential_type)

        # Mock SecretService via create_secret_service
        mock_ss = MagicMock()
        mock_ss.retrieve_secret = AsyncMock(return_value={"token": "my-secret-token"})
        mock_create_ss.return_value = mock_ss

        result = await resolve_workflow_credentials({ACTIVITY_ID: CREDENTIAL_ID})

        assert ACTIVITY_ID in result
        assert result[ACTIVITY_ID]["credential_id"] == CREDENTIAL_ID
        assert result[ACTIVITY_ID]["credential_type_name"] == "HTTP Bearer Token"
        assert result[ACTIVITY_ID]["extra_vars"]["bearer_token"] == "my-secret-token"  # noqa: S105
        assert result[ACTIVITY_ID]["_secret_values"] == ["my-secret-token"]

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_secret_values_excludes_non_secret_fields(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
        mock_credential: MagicMock,
    ) -> None:
        """Test that _secret_values only includes fields marked secret=True."""
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        # Basic auth has both secret (password) and non-secret (username) fields
        mock_cred_type = MagicMock()
        mock_cred_type.name = "HTTP Basic Auth"
        mock_cred_type.inputs = {
            "fields": [
                {"id": "username", "label": "Username", "type": "string", "secret": False},
                {"id": "password", "label": "Password", "type": "string", "secret": True},
            ],
        }
        mock_cred_type.injectors = {
            "extra_vars": {"auth_type": "basic", "basic_username": "{{username}}", "basic_password": "{{password}}"},
            "env": {},
            "file": {},
        }

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_credential
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.get = AsyncMock(return_value=mock_cred_type)

        mock_ss = MagicMock()
        mock_ss.retrieve_secret = AsyncMock(return_value={"username": "admin", "password": "hunter2"})
        mock_create_ss.return_value = mock_ss

        result = await resolve_workflow_credentials({ACTIVITY_ID: CREDENTIAL_ID})

        # Only password (secret=True) should be in _secret_values, not username
        assert "hunter2" in result[ACTIVITY_ID]["_secret_values"]
        assert "admin" not in result[ACTIVITY_ID]["_secret_values"]

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_secret_values_excludes_short_values(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
        mock_credential: MagicMock,
        mock_credential_type: MagicMock,
    ) -> None:
        """Test that _secret_values excludes values shorter than 4 chars."""
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_credential
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.get = AsyncMock(return_value=mock_credential_type)

        mock_ss = MagicMock()
        mock_ss.retrieve_secret = AsyncMock(return_value={"token": "ab"})  # Too short
        mock_create_ss.return_value = mock_ss

        result = await resolve_workflow_credentials({ACTIVITY_ID: CREDENTIAL_ID})
        assert result[ACTIVITY_ID]["_secret_values"] == []

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_disabled_credential_raises_non_retryable(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
        mock_credential: MagicMock,
    ) -> None:
        """Test disabled credential raises non-retryable ApplicationError."""
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        mock_credential.enabled = False

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_credential
        mock_session.exec = AsyncMock(return_value=mock_result)

        with pytest.raises(ApplicationError, match="disabled"):
            await resolve_workflow_credentials({ACTIVITY_ID: CREDENTIAL_ID})

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_missing_credential_raises_non_retryable(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
    ) -> None:
        """Test missing credential raises non-retryable ApplicationError."""
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec = AsyncMock(return_value=mock_result)

        with pytest.raises(ApplicationError, match="not found"):
            await resolve_workflow_credentials({ACTIVITY_ID: CREDENTIAL_ID})

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_no_secret_id_raises_non_retryable(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
        mock_credential: MagicMock,
    ) -> None:
        """Test credential with no secret_id raises non-retryable error."""
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        mock_credential.secret_id = None

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_credential
        mock_session.exec = AsyncMock(return_value=mock_result)

        with pytest.raises(ApplicationError, match="no stored secret"):
            await resolve_workflow_credentials({ACTIVITY_ID: CREDENTIAL_ID})

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_decryption_failure_raises_non_retryable(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
        mock_credential: MagicMock,
    ) -> None:
        """Test decryption failure raises non-retryable ApplicationError."""
        from syntara.core.lib.encryption import EncryptionError
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_credential
        mock_session.exec = AsyncMock(return_value=mock_result)

        mock_ss = MagicMock()
        mock_ss.retrieve_secret = AsyncMock(side_effect=EncryptionError("decryption failed"))
        mock_create_ss.return_value = mock_ss

        with pytest.raises(ApplicationError, match="Failed to decrypt"):
            await resolve_workflow_credentials({ACTIVITY_ID: CREDENTIAL_ID})


class TestCrossProjectCredentialResolution:
    """AAP-79159: credential resolution rejects cross-project references."""

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_cross_project_credential_rejected_at_runtime(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
        mock_credential: MagicMock,
    ) -> None:
        """Credential from project A must be rejected when workflow belongs to project B."""
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_credential
        mock_session.exec = AsyncMock(return_value=mock_result)

        with pytest.raises(ApplicationError, match="does not belong to workflow project"):
            await resolve_workflow_credentials(
                {ACTIVITY_ID: CREDENTIAL_ID},
                project_id=PROJECT_B_ID,
            )

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_same_project_credential_allowed(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
        mock_credential: MagicMock,
        mock_credential_type: MagicMock,
    ) -> None:
        """Credential from the same project must resolve successfully."""
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_credential
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.get = AsyncMock(return_value=mock_credential_type)

        mock_ss = MagicMock()
        mock_ss.retrieve_secret = AsyncMock(return_value={"token": "secret"})
        mock_create_ss.return_value = mock_ss

        result = await resolve_workflow_credentials(
            {ACTIVITY_ID: CREDENTIAL_ID},
            project_id=PROJECT_A_ID,
        )
        assert ACTIVITY_ID in result
        assert result[ACTIVITY_ID]["credential_id"] == CREDENTIAL_ID

    @pytest.mark.asyncio
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity._session_factory")
    @patch("syntara.workflows.workflow_engine.activities.credential_resolution_activity.create_secret_service")
    async def test_no_project_id_allows_resolution_for_backward_compat(
        self,
        mock_create_ss: MagicMock,
        mock_session_local: MagicMock,
        mock_credential: MagicMock,
        mock_credential_type: MagicMock,
    ) -> None:
        """When project_id is None (legacy/in-flight), credential resolves without project check."""
        from syntara.workflows.workflow_engine.activities.credential_resolution_activity import (
            resolve_workflow_credentials,
        )

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_credential
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.get = AsyncMock(return_value=mock_credential_type)

        mock_ss = MagicMock()
        mock_ss.retrieve_secret = AsyncMock(return_value={"token": "secret"})
        mock_create_ss.return_value = mock_ss

        result = await resolve_workflow_credentials({ACTIVITY_ID: CREDENTIAL_ID})
        assert ACTIVITY_ID in result
