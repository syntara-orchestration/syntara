"""OpenShift integrations validate the scoped executor credential safely."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from syntara.integrations.adapters.openshift import OpenShiftAdapter
from syntara.integrations.adapters.protocol import HealthCheckErrorType
from syntara.integrations.models.integration import IntegrationCreate, IntegrationType
from syntara.integrations.models.integration_configuration import OpenShiftConfiguration


def _config() -> OpenShiftConfiguration:
    return OpenShiftConfiguration(
        base_url="https://api.example.com:6443",
        namespace="ep-dev-workers",
        execution_target_id=uuid4(),
    )


def test_openshift_configuration_never_accepts_plaintext_http_or_insecure_tls() -> None:
    with pytest.raises(ValidationError):
        OpenShiftConfiguration(base_url="http://api.example.com", namespace="workers", execution_target_id=uuid4())
    with pytest.raises(ValidationError):
        OpenShiftConfiguration(
            base_url="https://api.example.com",
            namespace="workers",
            execution_target_id=uuid4(),
            insecure_skip_tls_verify=True,
        )


def test_integration_discriminator_accepts_openshift() -> None:
    integration = IntegrationCreate(
        name="Dev OpenShift",
        integration_type=IntegrationType.OPENSHIFT,
        configuration=_config(),
    )
    assert integration.configuration.integration_type == "openshift"


@pytest.mark.asyncio
async def test_adapter_sends_token_only_to_namespace_pods_api() -> None:
    response = httpx.Response(200, json={"items": []}, request=httpx.Request("GET", "https://api.example.com"))
    client = AsyncMock()
    client.get.return_value = response
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    with patch("syntara.integrations.adapters.openshift.httpx.AsyncClient", return_value=context):
        result = await OpenShiftAdapter(_config()).validate({"bearer_token": "test-token"}, 5)

    assert result.success is True
    url = client.get.call_args.args[0]
    assert url.endswith("/api/v1/namespaces/ep-dev-workers/pods")
    assert client.get.call_args.kwargs["headers"] == {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_adapter_rejects_missing_token_without_network() -> None:
    with patch("syntara.integrations.adapters.openshift.httpx.AsyncClient") as client:
        result = await OpenShiftAdapter(_config()).validate({}, 5)

    assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
    assert "token" in (result.error or "").lower()
    client.assert_not_called()
