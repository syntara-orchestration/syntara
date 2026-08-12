"""Integration tests for SA credential token invalidation.

When a service account credential is disabled or deleted, tokens issued
from that credential must be rejected by StaleTokenMiddleware with
``SA_CREDENTIAL_DISABLED``, and the corresponding audit event must fire.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from syntara.audit.outbox.worker import get_outbox_worker

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from httpx import AsyncClient

    from syntara.audit.models.audit_event import AuditEvent
    from syntara.core.models.user import User

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _find_events(mock_otel_emit: MagicMock, event_action: str) -> list[AuditEvent]:
    matches = []
    for call in mock_otel_emit.call_args_list:
        event: AuditEvent = call.args[0]
        if event.event_action == event_action:
            matches.append(event)
    return matches


async def _create_sa(
    base_client: AsyncClient,
    headers: dict[str, str],
    project_id: UUID,
) -> dict[str, Any]:
    resp = await base_client.post(
        "/api/v1/service_accounts",
        json={
            "name": f"cred-inv-test-{uuid4().hex[:8]}",
            "project_id": str(project_id),
        },
        headers=headers,
    )
    assert resp.status_code == 201, f"SA create failed: {resp.status_code} {resp.text}"
    body: dict[str, Any] = resp.json()
    return body


async def _create_credential(
    base_client: AsyncClient,
    headers: dict[str, str],
    service_account_id: str,
) -> dict[str, Any]:
    resp = await base_client.post(
        f"/api/v1/service_accounts/{service_account_id}/credentials",
        json={"credential_type": "client_credentials"},
        headers=headers,
    )
    assert resp.status_code == 201, f"Credential create failed: {resp.status_code} {resp.text}"
    body: dict[str, Any] = resp.json()
    return body


async def _obtain_sa_token(
    base_client: AsyncClient,
    identifier: str,
    client_secret: str,
) -> str:
    resp = await base_client.post(
        "/api/v1/auth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": identifier,
            "client_secret": client_secret,
        },
    )
    assert resp.status_code == 200, f"Token grant failed: {resp.status_code} {resp.text}"
    token: str = resp.json()["access_token"]
    return token


class TestCredentialDisableTokenInvalidation:
    """Disabling a credential invalidates tokens from that credential."""

    @patch("syntara.audit.outbox.worker._build_otel_log_record")
    async def test_disabled_credential_token_rejected(
        self,
        mock_build_otel_log_record: MagicMock,
        base_client: AsyncClient,
        admin_user: User,
        create_jwt_for_user: Callable[[User], str],
        test_project_id: UUID,
    ) -> None:
        token = create_jwt_for_user(admin_user)
        headers = {"Authorization": f"Bearer {token}"}

        sa = await _create_sa(base_client, headers, test_project_id)
        cred = await _create_credential(base_client, headers, sa["id"])

        try:
            sa_token = await _obtain_sa_token(base_client, cred["identifier"], cred["client_secret"])

            me_resp = await base_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {sa_token}"})
            assert me_resp.status_code == 200, f"Token should work before disable: {me_resp.status_code}"

            disable_resp = await base_client.post(
                f"/api/v1/service_accounts/{sa['id']}/credentials/{cred['id']}/disable",
                headers=headers,
            )
            assert disable_resp.status_code == 200, f"Disable failed: {disable_resp.status_code} {disable_resp.text}"

            mock_build_otel_log_record.reset_mock()

            with patch("syntara.auth.middleware._check_cred_status", return_value="disabled"):
                me_resp2 = await base_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {sa_token}"})
            assert me_resp2.status_code == 401, f"Expected 401 after disable, got {me_resp2.status_code}"
            assert me_resp2.json()["code"] == "SA_CREDENTIAL_DISABLED"

            await get_outbox_worker().drain()
            events = _find_events(mock_build_otel_log_record, "disabled_sa_credential_rejected")
            assert len(events) >= 1, (
                f"Expected disabled_sa_credential_rejected event, found: "
                f"{[c.args[0].event_action for c in mock_build_otel_log_record.call_args_list]}"
            )
        finally:
            await base_client.delete(f"/api/v1/service_accounts/{sa['id']}", headers=headers)


class TestCredentialDeleteTokenInvalidation:
    """Deleting a credential invalidates tokens from that credential."""

    @patch("syntara.audit.outbox.worker._build_otel_log_record")
    async def test_deleted_credential_token_rejected(
        self,
        mock_build_otel_log_record: MagicMock,
        base_client: AsyncClient,
        admin_user: User,
        create_jwt_for_user: Callable[[User], str],
        test_project_id: UUID,
    ) -> None:
        token = create_jwt_for_user(admin_user)
        headers = {"Authorization": f"Bearer {token}"}

        sa = await _create_sa(base_client, headers, test_project_id)
        cred = await _create_credential(base_client, headers, sa["id"])

        try:
            sa_token = await _obtain_sa_token(base_client, cred["identifier"], cred["client_secret"])

            me_resp = await base_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {sa_token}"})
            assert me_resp.status_code == 200, f"Token should work before delete: {me_resp.status_code}"

            delete_resp = await base_client.delete(
                f"/api/v1/service_accounts/{sa['id']}/credentials/{cred['id']}",
                headers=headers,
            )
            assert delete_resp.status_code == 204, f"Delete failed: {delete_resp.status_code} {delete_resp.text}"

            mock_build_otel_log_record.reset_mock()

            with patch("syntara.auth.middleware._check_cred_status", return_value=None):
                me_resp2 = await base_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {sa_token}"})
            assert me_resp2.status_code == 401, f"Expected 401 after delete, got {me_resp2.status_code}"
            assert me_resp2.json()["code"] == "SA_CREDENTIAL_DISABLED"

            await get_outbox_worker().drain()
            events = _find_events(mock_build_otel_log_record, "disabled_sa_credential_rejected")
            assert len(events) >= 1, (
                f"Expected disabled_sa_credential_rejected event, found: "
                f"{[c.args[0].event_action for c in mock_build_otel_log_record.call_args_list]}"
            )
        finally:
            await base_client.delete(f"/api/v1/service_accounts/{sa['id']}", headers=headers)
