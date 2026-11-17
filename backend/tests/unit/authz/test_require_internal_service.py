"""Tests for the ``require_internal_service`` mTLS gate."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from syntara.authz.dependencies import require_internal_service
from syntara.authz.exceptions import AuthorizationDeniedError

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

SettingsOverride = Callable[..., AbstractContextManager[object]]


def _make_request(**state: object) -> MagicMock:
    request = MagicMock()
    # SimpleNamespace so a missing attribute is really missing (MagicMock would be truthy).
    request.state = SimpleNamespace(**state)
    request.url.path = "/api/v1/form_prompts"
    return request


async def test_allows_cert_authenticated_service(override_settings: SettingsOverride) -> None:
    request = _make_request(is_cert_authenticated=True, cert_cn="worker.ao.svc")

    with override_settings(s2s_tls_enabled=True):
        await require_internal_service(request)


@pytest.mark.parametrize(
    "state",
    [
        pytest.param({}, id="no-cert-state"),
        pytest.param({"is_cert_authenticated": False, "cert_cn": None}, id="cert-not-allowlisted"),
    ],
)
async def test_rejects_non_cert_callers(override_settings: SettingsOverride, state: dict[str, object]) -> None:
    request = _make_request(**state)

    with override_settings(s2s_tls_enabled=True), pytest.raises(AuthorizationDeniedError, match="internal services"):
        await require_internal_service(request)


async def test_fails_closed_when_s2s_tls_disabled(override_settings: SettingsOverride) -> None:
    # Even a request claiming cert auth is rejected when TLS is off: nothing could have verified it.
    request = _make_request(is_cert_authenticated=True, cert_cn="worker.ao.svc")

    with override_settings(s2s_tls_enabled=False), pytest.raises(AuthorizationDeniedError, match="disabled"):
        await require_internal_service(request)
