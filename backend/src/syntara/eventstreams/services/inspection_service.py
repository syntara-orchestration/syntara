"""Preflight unsaved Kafka Subscribe bindings without activating consumption."""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from syntara.core.exceptions import SafeValueError
from syntara.core.services import BaseService
from syntara.credentials.lib.kafka_connection import resolve_listener_kafka_login
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.adapters.kafka_preflight import PREFLIGHT_TIMEOUT_SECONDS, test_kafka_connection
from syntara.eventstreams.models.responses import EventSubscriptionTestResponse
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import Integration
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.services.workflow_service import WorkflowService

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.authz.evaluator import AuthzEvaluator
    from syntara.core.models import User
    from syntara.core.services.secret_service import SecretService


class EventSubscriptionInspectionService(BaseService):
    """No persistence, publication or consumer activation operations."""

    def __init__(
        self,
        session: "AsyncSession",
        user: "User",
        evaluator: "AuthzEvaluator",
        secret_service: "SecretService",
        *,
        is_cert_authenticated: bool = False,
    ) -> None:
        """Reuse workflow resource checks and the listener credential resolver.

        Args:
            session: Database session.
            user: The authenticated user (or service principal).
            evaluator: Authorization evaluator for in-service authz checks.
            secret_service: Secret resolver for credential decryption.
            is_cert_authenticated: True when the caller authenticated via a service
                certificate. Forwarded to WorkflowService so OPA checks in
                validate_event_subscribe_access honour the cert-auth bypass.

        """
        super().__init__(session, user)
        self.workflows = WorkflowService(session, user, evaluator, is_cert_authenticated=is_cert_authenticated)
        self.secret_service = secret_service

    async def test_unsaved(
        self, workflow_id: UUID, parameters: KafkaSubscribeParameters
    ) -> EventSubscriptionTestResponse:
        """Check all references before decrypting the explicitly selected credential."""
        workflow = await self.workflows.get_workflow_by_id(workflow_id)
        await self.workflows.validate_event_subscribe_access(parameters.model_dump(mode="json"), workflow.project_id)
        integration = await self.session.get(Integration, parameters.integration_id)
        if integration is None or not isinstance(integration.configuration, KafkaConfiguration):
            msg = "Selected Kafka Integration is unavailable"
            raise SafeValueError(msg)
        try:
            async with asyncio.timeout(PREFLIGHT_TIMEOUT_SECONDS):
                # Preserve the pre-secret address check without blocking the API
                # loop. Socket creation rechecks and pins DNS under this deadline.
                try:
                    await asyncio.to_thread(validate_integration_configuration_no_ssrf, integration.configuration)
                except ValueError as exc:
                    msg = "bootstrap_servers must not resolve to a private, reserved, or cloud metadata address."
                    raise SafeValueError(msg) from exc
                credential = await resolve_listener_kafka_login(
                    self.session,
                    self.secret_service,
                    runtime_credential_id=parameters.credential_id,
                    security_protocol=integration.configuration.security_protocol,
                )
                return await test_kafka_connection(integration.configuration, credential or {}, parameters.topic)
        except TimeoutError:
            return EventSubscriptionTestResponse(success=False, checked_at=datetime.now(UTC), error_code="timeout")
