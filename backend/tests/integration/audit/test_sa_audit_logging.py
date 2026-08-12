"""Integration tests for service account audit event logging (API-26,27,28,29).

Tests verify that service account lifecycle operations emit audit events
with correct metadata and without leaking secrets.


Covers:
  API-26: Audit log — service account created (event present, no secret leakage)
  API-27: Audit log — secret rotated (event present, no secret values in payload)
  API-28: Audit log — auth success and failure (both event types, no token/secret in payload)
  API-29: Audit log — disable and delete (lifecycle event entries)

Pattern follows tests/integration/api/test_audit_middleware.py: mock the OTEL
emitter, drain the outbox, and inspect captured AuditEvent objects.
"""

from __future__ import annotations

import json
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

_SECRET_FIELD_NAMES = {"client_secret", "hashed_secret", "old_hashed_secret", "plaintext"}


def _find_events(
    mock_otel_emit: MagicMock,
    event_action: str,
) -> list[AuditEvent]:
    """Find all audit events matching a given event_action."""
    matches = []
    for call in mock_otel_emit.call_args_list:
        event: AuditEvent = call.args[0]
        if event.event_action == event_action:
            matches.append(event)
    return matches


def _assert_no_secrets_in_event(event: AuditEvent, *secret_values: str) -> None:
    """Assert that an audit event does not contain plaintext secrets."""
    event_str = json.dumps(event.__dict__, default=str)
    for value in secret_values:
        assert value not in event_str, f"Secret value leaked into audit event '{event.event_action}'"
    event_str_lower = event_str.lower()
    for keyword in _SECRET_FIELD_NAMES:
        assert keyword not in event_str_lower, f"Secret keyword '{keyword}' found in audit event '{event.event_action}'"


async def _create_sa(
    base_client: AsyncClient,
    headers: dict[str, str],
    project_id: UUID,
) -> dict[str, Any]:
    """Create a service account via API and return the parsed response body."""
    resp = await base_client.post(
        "/api/v1/service_accounts",
        json={
            "name": f"audit-test-sa-{uuid4().hex[:8]}",
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
    """Create a credential for a service account and return the response body."""
    resp = await base_client.post(
        f"/api/v1/service_accounts/{service_account_id}/credentials",
        json={"credential_type": "client_credentials"},
        headers=headers,
    )
    assert resp.status_code == 201, f"Credential create failed: {resp.status_code} {resp.text}"
    body: dict[str, Any] = resp.json()
    return body


class TestAuditSACreated:
    """API-26: Audit log — service account created (event present, no secret leakage)."""

    @patch("syntara.audit.outbox.worker._build_otel_log_record")
    async def test_create_emits_audit_event_without_secrets(
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

        try:
            await get_outbox_worker().drain()

            events = _find_events(mock_build_otel_log_record, "service_account_create")
            assert len(events) >= 1, (
                f"Expected service_account_create event, found none among "
                f"{[c.args[0].event_action for c in mock_build_otel_log_record.call_args_list]}"
            )

            event = events[-1]
            assert event.event_category == "user_action"
            assert event.event_status == "success"
            assert event.actor_id == admin_user.id
            _assert_no_secrets_in_event(event)
        finally:
            await base_client.delete(f"/api/v1/service_accounts/{sa['id']}", headers=headers)


class TestAuditSecretRotated:
    """API-27: Audit log — secret rotated (event present, no secret values in payload)."""

    @patch("syntara.audit.outbox.worker._build_otel_log_record")
    async def test_rotate_emits_audit_event_without_secrets(
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
            mock_build_otel_log_record.reset_mock()

            rotate_resp = await base_client.post(
                f"/api/v1/service_accounts/{sa['id']}/credentials/{cred['id']}/rotate",
                json={},
                headers=headers,
            )
            assert rotate_resp.status_code == 200, f"Rotate failed: {rotate_resp.status_code} {rotate_resp.text}"
            new_secret = rotate_resp.json().get("client_secret", "")

            await get_outbox_worker().drain()

            events = _find_events(mock_build_otel_log_record, "sa_credential_rotate")
            assert len(events) >= 1, (
                f"Expected sa_credential_rotate event, found none among "
                f"{[c.args[0].event_action for c in mock_build_otel_log_record.call_args_list]}"
            )

            for event in events:
                _assert_no_secrets_in_event(event, cred["client_secret"], new_secret)
        finally:
            await base_client.delete(f"/api/v1/service_accounts/{sa['id']}", headers=headers)


class TestAuditAuthSuccessAndFailure:
    """API-28: Audit log — auth success and failure (both event types, no token/secret in payload)."""

    @patch("syntara.audit.outbox.worker._build_otel_log_record")
    async def test_auth_success_emits_login_event(
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
            mock_build_otel_log_record.reset_mock()

            auth_resp = await base_client.post(
                "/api/v1/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": cred["identifier"],
                    "client_secret": cred["client_secret"],
                },
            )
            assert auth_resp.status_code == 200, f"Token grant failed: {auth_resp.status_code} {auth_resp.text}"
            issued_token = auth_resp.json()["access_token"]

            await get_outbox_worker().drain()

            login_events = _find_events(mock_build_otel_log_record, "login")
            success_events = [e for e in login_events if e.event_status == "success"]
            assert len(success_events) >= 1, "Expected at least one successful login audit event"

            for event in success_events:
                _assert_no_secrets_in_event(event, cred["client_secret"], issued_token)
        finally:
            await base_client.delete(f"/api/v1/service_accounts/{sa['id']}", headers=headers)

    @patch("syntara.audit.outbox.worker._build_otel_log_record")
    async def test_auth_failure_emits_login_event(
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
            mock_build_otel_log_record.reset_mock()

            auth_resp = await base_client.post(
                "/api/v1/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": cred["identifier"],
                    "client_secret": "wrong-secret-value",
                },
            )
            assert auth_resp.status_code == 401

            await get_outbox_worker().drain()

            login_events = _find_events(mock_build_otel_log_record, "login")
            failure_events = [e for e in login_events if e.event_status == "error"]
            assert len(failure_events) >= 1, "Expected at least one failed login audit event"

            for event in failure_events:
                _assert_no_secrets_in_event(event, cred["client_secret"], "wrong-secret-value")
        finally:
            await base_client.delete(f"/api/v1/service_accounts/{sa['id']}", headers=headers)


class TestAuditDisableAndDelete:
    """API-29: Audit log — disable and delete (lifecycle event entries)."""

    @patch("syntara.audit.outbox.worker._build_otel_log_record")
    async def test_disable_emits_audit_event(
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

        try:
            mock_build_otel_log_record.reset_mock()

            disable_resp = await base_client.post(
                f"/api/v1/service_accounts/{sa['id']}/disable",
                headers=headers,
            )
            assert disable_resp.status_code == 200, f"Disable failed: {disable_resp.status_code} {disable_resp.text}"

            await get_outbox_worker().drain()

            events = _find_events(mock_build_otel_log_record, "service_account_disable")
            assert len(events) >= 1, (
                f"Expected service_account_disable event, found none among "
                f"{[c.args[0].event_action for c in mock_build_otel_log_record.call_args_list]}"
            )
            assert events[-1].event_category == "user_action"
            assert events[-1].actor_id == admin_user.id
        finally:
            await base_client.delete(f"/api/v1/service_accounts/{sa['id']}", headers=headers)

    @patch("syntara.audit.outbox.worker._build_otel_log_record")
    async def test_delete_emits_audit_event(
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

        mock_build_otel_log_record.reset_mock()

        delete_resp = await base_client.delete(
            f"/api/v1/service_accounts/{sa['id']}",
            headers=headers,
        )
        assert delete_resp.status_code == 204, f"Delete failed: {delete_resp.status_code} {delete_resp.text}"

        await get_outbox_worker().drain()

        events = _find_events(mock_build_otel_log_record, "service_account_delete")
        assert len(events) >= 1, (
            f"Expected service_account_delete event, found none among "
            f"{[c.args[0].event_action for c in mock_build_otel_log_record.call_args_list]}"
        )
        assert events[-1].event_category == "user_action"
        assert events[-1].actor_id == admin_user.id
