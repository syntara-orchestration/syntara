"""E2E tests for global revocation behavior.

The global revocation system uses a TTL-adjusted comparison:
tokens issued before ``revocation_ts + CACHE_TTL`` are rejected.
This means revocation is **eventually consistent** — nodes with a
stale cached value may still accept pre-revocation tokens for up
to ``_CACHE_TTL`` seconds.  After that window, enforcement is
guaranteed.

API mapping:
- POST /admin/revocation — set global revocation timestamp
- GET  /admin/revocation — read current revocation timestamp
- POST /auth/login       — create a session
- POST /auth/refresh     — refresh an access token
- GET  /auth/me          — validate an access token
"""

from __future__ import annotations

import time
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from orchestrator_test_sdk.e2e.auth import (
    assert_refresh_succeeds,
    get_current_user_with_token,
    local_login_session,
    refresh_with_cookies,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models.user_read import UserRead

pytestmark = [pytest.mark.e2e, pytest.mark.global_revocation]

_CACHE_TTL = 10
REVOCATION_RETRY_COUNT = 5


def _wait_for_cache_expiry() -> None:
    """Sleep long enough for all nodes' TTL caches to expire."""
    time.sleep(_CACHE_TTL + 1)


@pytest.fixture(scope="module", autouse=True)
def _drain_revocation_window_after_module() -> Generator[None, None, None]:
    """Wait for the global revocation TTL to clear after all tests in this module.

    test_revocation_timestamp_readable_after_set calls _revoke_all() as its
    last action without a subsequent _wait_for_cache_expiry().  Without this
    fixture, the 10-second rejection window bleeds into the next test module,
    causing TOKEN_GLOBALLY_REVOKED failures on fresh tokens.
    """
    yield
    _wait_for_cache_expiry()


_API_HEALTH_TIMEOUT = 15.0


def _wait_for_api_healthy(syntara_api: SyntaraApiRegistry) -> None:
    """Poll the API until it responds with 200, absorbing any post-revocation instability."""
    deadline = time.monotonic() + _API_HEALTH_TIMEOUT
    while True:
        try:
            resp = syntara_api.settings.list(limit=1)
            if resp.status_code == HTTPStatus.OK:
                return
        except Exception:
            pass
        if time.monotonic() >= deadline:
            pytest.fail(f"API not healthy after {_API_HEALTH_TIMEOUT}s following global revocation")
        time.sleep(0.5)


def _revoke_all(syntara_api: SyntaraApiRegistry) -> None:
    """Revoke all sessions via the generated API client, then wait for the API to stabilize.

    Global revocation invalidates every cached session on the server.  In the
    resource-constrained KinD CI cluster this can temporarily overwhelm the API
    pod (cache invalidation storm, ``_AutoRefreshAuth`` re-authentication
    traffic), causing nginx to return 502 Bad Gateway on subsequent requests.

    After the revocation succeeds we poll the API until it responds with 200,
    ensuring callers always see a stable server.
    """
    response = syntara_api.admin.revoke_all_sessions()
    assert response.status_code == HTTPStatus.OK, (
        f"Failed to set global revocation: {response.status_code} {response.content!r}"
    )
    _wait_for_api_healthy(syntara_api)


def assert_refresh_unauthorized_consistently(
    base_url: str,
    cookies: dict[str, str],
    *,
    attempts: int = REVOCATION_RETRY_COUNT,
    label: str = "",
) -> None:
    """Every refresh attempt must return 401 — no stale-cache flickers allowed.

    Callers are responsible for waiting until the cache TTL has elapsed
    before calling this function.
    """
    for i in range(1, attempts + 1):
        resp = refresh_with_cookies(base_url, cookies)
        assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
            f"[{label} attempt {i}/{attempts}] Expected refresh 401, got {resp.status_code}: {resp.content!r}"
        )


def assert_access_token_unauthorized(
    base_url: str,
    access_token: str,
    *,
    label: str = "",
) -> None:
    """GET /auth/me must return 401 for a revoked access token."""
    resp = get_current_user_with_token(base_url, access_token)
    assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
        f"[{label}] Expected /auth/me 401, got {resp.status_code}: {resp.content!r}"
    )


class TestGlobalRevocation:
    """Global revocation invalidates all pre-existing sessions after cache TTL expires."""

    def test_global_revocation_invalidates_all_sessions(
        self,
        syntara_api: SyntaraApiRegistry,
        syntara_base_url: str,
        local_user_factory: Callable[..., tuple[UserRead, str]],
    ) -> None:
        """All pre-revocation tokens (access and refresh) must be rejected after cache TTL."""
        user_a, pw_a = local_user_factory(first_name="GlobalRev", last_name="UserA")
        user_b, pw_b = local_user_factory(first_name="GlobalRev", last_name="UserB")

        token_a, cookies_a = local_login_session(syntara_base_url, user_a.username, pw_a)
        token_b, cookies_b = local_login_session(syntara_base_url, user_b.username, pw_b)

        assert_refresh_succeeds(syntara_base_url, cookies_a)
        assert_refresh_succeeds(syntara_base_url, cookies_b)

        _revoke_all(syntara_api)
        _wait_for_cache_expiry()

        assert_refresh_unauthorized_consistently(syntara_base_url, cookies_a, label="user_a")
        assert_refresh_unauthorized_consistently(syntara_base_url, cookies_b, label="user_b")

        assert_access_token_unauthorized(syntara_base_url, token_a, label="user_a access")
        assert_access_token_unauthorized(syntara_base_url, token_b, label="user_b access")

    def test_sessions_created_after_revocation_are_valid(
        self,
        syntara_api: SyntaraApiRegistry,
        syntara_base_url: str,
        local_user_factory: Callable[..., tuple[UserRead, str]],
    ) -> None:
        """Sessions created after the TTL window must work normally."""
        user, pw = local_user_factory(first_name="GlobalRev", last_name="PostRevoke")

        _, cookies_before = local_login_session(syntara_base_url, user.username, pw)

        _revoke_all(syntara_api)
        _wait_for_cache_expiry()

        assert_refresh_unauthorized_consistently(syntara_base_url, cookies_before, label="pre-revoke")

        _, cookies_after = local_login_session(syntara_base_url, user.username, pw)
        assert_refresh_succeeds(syntara_base_url, cookies_after)

    def test_tokens_issued_during_ttl_window_are_rejected(
        self,
        syntara_api: SyntaraApiRegistry,
        syntara_base_url: str,
        local_user_factory: Callable[..., tuple[UserRead, str]],
    ) -> None:
        """Tokens obtained within the TTL window after revocation must also be rejected.

        The TTL-adjusted comparison ensures tokens issued during the
        cache-staleness window (revocation_ts to revocation_ts + CACHE_TTL)
        are treated as tainted and rejected once caches refresh.
        """
        user, pw = local_user_factory(first_name="GlobalRev", last_name="TTLWindow")

        _revoke_all(syntara_api)

        tainted_token, tainted_cookies = local_login_session(syntara_base_url, user.username, pw)

        _wait_for_cache_expiry()

        assert_access_token_unauthorized(syntara_base_url, tainted_token, label="tainted access")
        assert_refresh_unauthorized_consistently(syntara_base_url, tainted_cookies, label="tainted refresh")

        _, clean_cookies = local_login_session(syntara_base_url, user.username, pw)
        assert_refresh_succeeds(syntara_base_url, clean_cookies)

    def test_bruteforce_refresh_during_ttl_window_yields_unusable_token(
        self,
        syntara_api: SyntaraApiRegistry,
        syntara_base_url: str,
        local_user_factory: Callable[..., tuple[UserRead, str]],
    ) -> None:
        """Spam refresh with pre-revocation cookies during the TTL window.

        If any refresh succeeds (stale cache on a node), the obtained
        access token must still be rejected once the TTL window elapses.

        In a single-node deployment the cache is updated in-process, so
        revocation takes effect immediately and no refresh will succeed
        during the window.  The test accepts this as a valid outcome —
        the stale-cache race only manifests with multiple API nodes
        whose caches expire independently.  Either way, after the TTL
        elapses all tokens must be rejected.
        """
        from syntara_api_client.models.access_token_response import AccessTokenResponse

        user, pw = local_user_factory(first_name="GlobalRev", last_name="BruteForce")

        _, cookies = local_login_session(syntara_base_url, user.username, pw)
        assert_refresh_succeeds(syntara_base_url, cookies)

        _revoke_all(syntara_api)

        captured_tokens: list[str] = []
        deadline = time.monotonic() + _CACHE_TTL
        while time.monotonic() < deadline:
            resp = refresh_with_cookies(syntara_base_url, cookies)
            if resp.status_code == HTTPStatus.OK and isinstance(resp.parsed, AccessTokenResponse):
                captured_tokens.append(resp.parsed.access_token)

        _wait_for_cache_expiry()

        if captured_tokens:
            for i, token in enumerate(captured_tokens):
                assert_access_token_unauthorized(
                    syntara_base_url,
                    token,
                    label=f"captured token {i + 1}/{len(captured_tokens)}",
                )

        assert_refresh_unauthorized_consistently(syntara_base_url, cookies, label="post-ttl refresh")

    def test_revocation_timestamp_readable_after_set(
        self,
        syntara_api: SyntaraApiRegistry,
    ) -> None:
        """GET /admin/revocation must return a non-null timestamp after POST."""
        _revoke_all(syntara_api)

        response = syntara_api.admin.get_global_revocation_timestamp()
        assert response.status_code == HTTPStatus.OK
        data = response.parsed
        assert data is not None
        assert data.revoked_before is not None
        assert data.updated_at is not None
