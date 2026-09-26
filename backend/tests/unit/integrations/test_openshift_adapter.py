"""OpenShift integration configuration and non-workload health checks."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from syntara.integrations.adapters.openshift import OpenShiftAdapter
from syntara.integrations.adapters.protocol import HealthCheckErrorType, ValidateResult
from syntara.integrations.models.integration import IntegrationCreate, IntegrationType
from syntara.integrations.models.integration_configuration import OpenShiftConfiguration
from syntara.integrations.services.integration_service import ALLOWED_CREDENTIAL_TYPES, CREDENTIAL_REQUIRED_TYPES


def _config() -> OpenShiftConfiguration:
    return OpenShiftConfiguration(base_url="https://api.example.com:6443", namespace="ep-dev-workers")


def _mock_client(response: httpx.Response) -> tuple[AsyncMock, MagicMock]:
    client = AsyncMock()
    client.post.return_value = response
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return client, context


@pytest.mark.parametrize(
    "invalid_url",
    ["http://api.example.com", "https://api.example.com/path", "https://api.example.com/?key=secret"],
)
def test_openshift_configuration_requires_https_host_url(invalid_url: str) -> None:
    with pytest.raises(ValidationError):
        OpenShiftConfiguration(base_url=invalid_url, namespace="workers")


@pytest.mark.parametrize("invalid_namespace", ["", "UPPERCASE", "bad/name", "-bad"])
def test_openshift_configuration_rejects_invalid_namespace(invalid_namespace: str) -> None:
    with pytest.raises(ValidationError):
        OpenShiftConfiguration(base_url="https://api.example.com", namespace=invalid_namespace)


@pytest.mark.parametrize("tls_override", [{"allow_http": True}, {"insecure_skip_tls_verify": True}])
def test_openshift_configuration_requires_verified_tls(tls_override: dict[str, bool]) -> None:
    with pytest.raises(ValidationError):
        OpenShiftConfiguration(base_url="https://api.example.com", namespace="workers", **tls_override)


def test_integration_accepts_openshift_without_execution_plane_target() -> None:
    integration = IntegrationCreate(
        name="Dev OpenShift",
        integration_type=IntegrationType.OPENSHIFT,
        configuration=_config(),
    )
    assert integration.configuration.integration_type == "openshift"
    assert ALLOWED_CREDENTIAL_TYPES[IntegrationType.OPENSHIFT] == {"HTTP Bearer Token"}
    assert IntegrationType.OPENSHIFT in CREDENTIAL_REQUIRED_TYPES
    with pytest.raises(ValidationError):
        OpenShiftConfiguration(base_url="https://api.example.com", namespace="workers", execution_target_id="unused")


@pytest.mark.asyncio
async def test_validate_checks_bearer_identity_without_accessing_pods() -> None:
    url = "https://api.example.com:6443/apis/authentication.k8s.io/v1/selfsubjectreviews"
    response = httpx.Response(
        201,
        json={"status": {"userInfo": {"username": "system:serviceaccount:workers:executor"}}},
        request=httpx.Request("POST", url),
    )
    client, context = _mock_client(response)
    with patch("syntara.integrations.adapters.openshift.httpx.AsyncClient", return_value=context) as client_type:
        result = await OpenShiftAdapter(_config()).validate({"bearer_token": "test-token"}, 5)

    assert result.success is True
    client_type.assert_called_once_with(verify=True, timeout=5, follow_redirects=False)
    client.post.assert_awaited_once_with(
        url,
        json={"apiVersion": "authentication.k8s.io/v1", "kind": "SelfSubjectReview"},
        headers={"Authorization": "Bearer test-token"},
    )


@pytest.mark.asyncio
async def test_validate_rejects_missing_token_without_network() -> None:
    with patch("syntara.integrations.adapters.openshift.httpx.AsyncClient") as client_type:
        result = await OpenShiftAdapter(_config()).validate({}, 5)

    assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
    client_type.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_validate_classifies_rejected_token_as_auth_failure(status: int) -> None:
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.example.com"))
    _, context = _mock_client(response)
    with patch("syntara.integrations.adapters.openshift.httpx.AsyncClient", return_value=context):
        result = await OpenShiftAdapter(_config()).validate({"bearer_token": "secret-token"}, 5)

    assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
    assert "secret-token" not in (result.error or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("user_info", [{}, {"username": "system:anonymous"}])
async def test_validate_rejects_unconfirmed_identity(user_info: dict[str, str]) -> None:
    response = httpx.Response(
        201,
        json={"status": {"userInfo": user_info}},
        request=httpx.Request("POST", "https://api.example.com"),
    )
    _, context = _mock_client(response)
    with patch("syntara.integrations.adapters.openshift.httpx.AsyncClient", return_value=context):
        result = await OpenShiftAdapter(_config()).validate({"bearer_token": "secret-token"}, 5)

    assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
    assert "secret-token" not in (result.error or "")


@pytest.mark.asyncio
async def test_validate_classifies_timeout() -> None:
    client, context = _mock_client(httpx.Response(201))
    client.post.side_effect = httpx.ReadTimeout("timed out")
    with patch("syntara.integrations.adapters.openshift.httpx.AsyncClient", return_value=context):
        result = await OpenShiftAdapter(_config()).validate({"bearer_token": "secret-token"}, 5)

    assert result.error_type == HealthCheckErrorType.TIMEOUT
    assert "secret-token" not in (result.error or "")


@pytest.mark.asyncio
async def test_validate_rejects_malformed_identity_response() -> None:
    response = httpx.Response(201, json={"status": []}, request=httpx.Request("POST", "https://api.example.com"))
    _, context = _mock_client(response)
    with patch("syntara.integrations.adapters.openshift.httpx.AsyncClient", return_value=context):
        result = await OpenShiftAdapter(_config()).validate({"bearer_token": "secret-token"}, 5)

    assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
    assert "secret-token" not in (result.error or "")


@pytest.mark.asyncio
async def test_discover_returns_no_workload_resources() -> None:
    adapter = OpenShiftAdapter(_config())
    with patch.object(adapter, "validate", new_callable=AsyncMock) as validate:
        validate.return_value = ValidateResult(success=True, checked_at=datetime.now(UTC))
        result = await adapter.discover({"bearer_token": "secret-token"}, 5)

    assert result.success is True
    assert result.discovered_tools is None
    assert result.discovered_models is None
