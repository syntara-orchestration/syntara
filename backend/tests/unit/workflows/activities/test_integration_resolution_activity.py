"""Tests for integration resolution Temporal activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import AAPConfiguration
from syntara.workflows.workflow_engine.activities.integration_resolution_activity import (
    _resolve_integration,
)


def _make_integration(
    *,
    integration_id: str = "int-123",
    name: str = "My AAP",
    integration_type: str = IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
    enabled: bool = True,
    base_url: str = "https://aap.example.com/",
    insecure_skip_tls_verify: bool = False,
    use_real_config: bool = True,
) -> MagicMock:
    integration = MagicMock()
    integration.id = integration_id
    integration.name = name
    integration.integration_type = integration_type
    integration.enabled = enabled
    if use_real_config:
        integration.configuration = AAPConfiguration(
            base_url=base_url,
            insecure_skip_tls_verify=insecure_skip_tls_verify,
        )
    return integration


class TestResolveIntegration:
    """Tests for _resolve_integration helper."""

    @pytest.mark.anyio
    async def test_happy_path_returns_url_and_ssl(self) -> None:
        integration = _make_integration()
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.one_or_none.return_value = integration
        session.exec.return_value = result_mock

        result = await _resolve_integration(session, "int-123")

        assert result == {"base_url": "https://aap.example.com", "verify_ssl": True, "ca_certificate": None}

    @pytest.mark.anyio
    async def test_strips_trailing_slash_from_url(self) -> None:
        integration = _make_integration(base_url="https://aap.example.com/")
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.one_or_none.return_value = integration
        session.exec.return_value = result_mock

        result = await _resolve_integration(session, "int-123")

        assert result["base_url"] == "https://aap.example.com"

    @pytest.mark.anyio
    async def test_insecure_skip_tls_sets_verify_ssl_false(self) -> None:
        integration = _make_integration(insecure_skip_tls_verify=True)
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.one_or_none.return_value = integration
        session.exec.return_value = result_mock

        result = await _resolve_integration(session, "int-123")

        assert result["verify_ssl"] is False

    @pytest.mark.anyio
    async def test_not_found_raises_application_error(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.one_or_none.return_value = None
        session.exec.return_value = result_mock

        with pytest.raises(ApplicationError, match="not found"):
            await _resolve_integration(session, "missing-id")

    @pytest.mark.anyio
    async def test_wrong_type_raises_application_error(self) -> None:
        integration = _make_integration(integration_type="llm_provider")
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.one_or_none.return_value = integration
        session.exec.return_value = result_mock

        with pytest.raises(ApplicationError, match="expected 'ansible_automation_platform'"):
            await _resolve_integration(session, "int-123")

    @pytest.mark.anyio
    async def test_disabled_raises_application_error(self) -> None:
        integration = _make_integration(enabled=False, name="Disabled AAP")
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.one_or_none.return_value = integration
        session.exec.return_value = result_mock

        with pytest.raises(ApplicationError, match="is disabled"):
            await _resolve_integration(session, "int-123")

    @pytest.mark.anyio
    async def test_invalid_config_type_raises_application_error(self) -> None:
        integration = _make_integration(use_real_config=False)
        integration.configuration = {"not": "an AAPConfiguration"}
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.one_or_none.return_value = integration
        session.exec.return_value = result_mock

        with pytest.raises(ApplicationError, match="invalid configuration type"):
            await _resolve_integration(session, "int-123")


class TestResolveWorkflowIntegrationActivity:
    """Tests for the Temporal activity wrapper resolve_workflow_integration."""

    @pytest.mark.anyio
    async def test_delegates_to_resolve_integration(self) -> None:
        from syntara.workflows.workflow_engine.activities.integration_resolution_activity import (
            resolve_workflow_integration,
        )

        expected = {"base_url": "https://aap.test", "verify_ssl": True}

        mock_session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.integration_resolution_activity._session_factory",
                return_value=mock_ctx,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.integration_resolution_activity._resolve_integration",
                new_callable=AsyncMock,
                return_value=expected,
            ) as mock_resolve,
            patch("temporalio.activity.info"),
        ):
            result = await resolve_workflow_integration("int-abc")

        assert result == expected
        mock_resolve.assert_awaited_once_with(mock_session, "int-abc")

    @pytest.mark.anyio
    async def test_reraises_application_error(self) -> None:
        from syntara.workflows.workflow_engine.activities.integration_resolution_activity import (
            resolve_workflow_integration,
        )

        mock_session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.integration_resolution_activity._session_factory",
                return_value=mock_ctx,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.integration_resolution_activity._resolve_integration",
                new_callable=AsyncMock,
                side_effect=ApplicationError("not found", non_retryable=True),
            ),
            patch("temporalio.activity.info"),
            pytest.raises(ApplicationError, match="not found"),
        ):
            await resolve_workflow_integration("int-abc")

    @pytest.mark.anyio
    async def test_wraps_generic_exception_as_application_error(self) -> None:
        from syntara.workflows.workflow_engine.activities.integration_resolution_activity import (
            resolve_workflow_integration,
        )

        mock_session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.integration_resolution_activity._session_factory",
                return_value=mock_ctx,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.integration_resolution_activity._resolve_integration",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB gone"),
            ),
            patch("temporalio.activity.info"),
            pytest.raises(ApplicationError, match=r"Database error.*RuntimeError"),
        ):
            await resolve_workflow_integration("int-abc")
