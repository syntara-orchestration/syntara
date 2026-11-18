"""Tests for the ``require_internal_service`` mTLS gate."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from syntara.authz.audit.internal_service_denied import InternalServiceDeniedEvent
from syntara.authz.dependencies import require_internal_service
from syntara.authz.exceptions import InternalServiceRequiredError

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

SettingsOverride = Callable[..., AbstractContextManager[object]]


def _make_request(state: dict[str, object], headers: dict[str, str] | None = None) -> MagicMock:
    request = MagicMock()
    # SimpleNamespace so a missing attribute is really missing (MagicMock would be truthy).
    request.state = SimpleNamespace(**state)
    request.url.path = "/api/v1/form_prompts"
    request.method = "POST"
    # Starlette Headers are case-insensitive and store lowercase keys.
    request.headers = {k.lower(): v for k, v in (headers or {}).items()}
    return request


@pytest.fixture
def dispatch() -> Iterator[MagicMock]:
    with patch("syntara.audit.dispatcher.AuditEventDispatcher.dispatch") as mock_dispatch:
        yield mock_dispatch


async def test_allows_cert_authenticated_service(override_settings: SettingsOverride, dispatch: MagicMock) -> None:
    request = _make_request({"is_cert_authenticated": True, "cert_cn": "worker.ao.svc"})

    with override_settings(s2s_tls_enabled=True):
        await require_internal_service(request)

    dispatch.assert_not_called()


async def test_rejects_cert_with_authorization_header(override_settings: SettingsOverride, dispatch: MagicMock) -> None:
    # A bearer token would win over the cert in get_current_user, so the request would run as the user.
    request = _make_request(
        {"is_cert_authenticated": True, "cert_cn": "worker.ao.svc"}, headers={"Authorization": "Bearer user-token"}
    )

    with override_settings(s2s_tls_enabled=True), pytest.raises(InternalServiceRequiredError) as exc_info:
        await require_internal_service(request)

    assert exc_info.value.reason == "authorization_header_present"
    dispatch.assert_called_once_with(
        InternalServiceDeniedEvent(
            reason="authorization_header_present",
            path="/api/v1/form_prompts",
            method="POST",
            cert_cn="worker.ao.svc",
        )
    )


@pytest.mark.parametrize(
    "state",
    [
        pytest.param({}, id="no-cert-state"),
        pytest.param({"is_cert_authenticated": False, "cert_cn": None}, id="cert-not-allowlisted"),
    ],
)
async def test_rejects_non_cert_callers(
    override_settings: SettingsOverride, dispatch: MagicMock, state: dict[str, object]
) -> None:
    request = _make_request(state)

    with (
        override_settings(s2s_tls_enabled=True),
        pytest.raises(InternalServiceRequiredError, match="internal services") as exc_info,
    ):
        await require_internal_service(request)

    assert exc_info.value.reason == "not_cert_authenticated"
    dispatch.assert_called_once()
    assert dispatch.call_args.args[0].reason == "not_cert_authenticated"


async def test_fails_closed_when_s2s_tls_disabled(override_settings: SettingsOverride, dispatch: MagicMock) -> None:
    # Even a request claiming cert auth is rejected when TLS is off: nothing could have verified it.
    request = _make_request({"is_cert_authenticated": True, "cert_cn": "worker.ao.svc"})

    with (
        override_settings(s2s_tls_enabled=False),
        pytest.raises(InternalServiceRequiredError, match="disabled") as exc_info,
    ):
        await require_internal_service(request)

    assert exc_info.value.reason == "s2s_tls_disabled"
    dispatch.assert_called_once()
