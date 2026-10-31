"""Resolve a Publish snapshot and recheck its resource availability before sends."""

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID

from aiokafka.errors import UnknownTopicOrPartitionError, for_code
from aiokafka.protocol.metadata import MetadataRequest
from sqlalchemy.exc import OperationalError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models.secret import EncryptedSecret
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.lib.kafka_connection import KAFKA_CONNECTION_TYPE_NAME, kafka_credential_required
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.adapters.kafka_preflight import NonCreatingMetadataRequest, _close, _connect
from syntara.integrations.adapters.kafka import KafkaAdapter
from syntara.integrations.lib.kafka_connection import approved_broker_addresses
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities.credential_resolution_activity import _resolve_single_credential
from syntara.workflows.workflow_engine.activities.integration_scope_activity import _validate_integrations
from syntara.workflows.workflow_engine.activities.kafka_publish_errors import (
    classify_publish_error,
    fail_publish,
    publish_failure,
)
from syntara.workflows.workflow_engine.constants import TEMPORAL_PAYLOAD_MAX_BYTES
from syntara.workflows.workflow_engine.models.kafka_publish import KafkaPublishParameters
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.utils.temporal_argument_size import temporal_argument_size

_session_factory = AsyncSessionLocal


async def current_publish_resources(
    session: AsyncSession, parameters: KafkaPublishParameters, project_id: str
) -> tuple[KafkaConfiguration, str]:
    """Check scope/enabled/type and derive a revision without reading secret values."""
    if not project_id:
        fail_publish("kafka_invalid_reference")
    integration_id = UUID(parameters.integration_id)
    await _validate_integrations(
        session, {integration_id}, {integration_id: IntegrationType.KAFKA}, project_id, "kafka_publish"
    )
    integration = await session.get(Integration, integration_id)
    if integration is None or not isinstance(integration.configuration, KafkaConfiguration):
        fail_publish("kafka_invalid_reference")
    config = integration.configuration
    revision: list[str] = [str(integration.id), str(integration.updated_at)]
    if parameters.credential_id is not None:
        credential = await session.get(Credential, UUID(parameters.credential_id))
        if credential is None or not credential.enabled or str(credential.project_id) != project_id:
            fail_publish("kafka_invalid_reference")
        credential_type = await session.get(CredentialType, credential.credential_type_id)
        if (
            credential_type is None
            or credential_type.name != KAFKA_CONNECTION_TYPE_NAME
            or credential.secret_id is None
        ):
            fail_publish("kafka_invalid_reference")
        secret_updated_at = (
            await session.exec(
                select(EncryptedSecret.updated_at).where(EncryptedSecret.secret_id == credential.secret_id)
            )
        ).one_or_none()
        if secret_updated_at is None:
            fail_publish("kafka_invalid_reference")
        revision.extend(
            str(value)
            for value in (
                credential.id,
                credential.updated_at,
                credential_type.id,
                credential_type.updated_at,
                credential.secret_id,
                secret_updated_at,
            )
        )
    elif kafka_credential_required(config.security_protocol):
        fail_publish("kafka_invalid_reference")
    return config, hashlib.sha256(json.dumps(revision).encode()).hexdigest()


async def check_publish_topic(config: KafkaConfiguration, credentials: dict[str, Any], topic: str) -> None:
    """Use Subscribe's explicit non-creating metadata protocol before the first send."""
    # Connection policy validation includes bootstrap DNS/SSRF checks.
    await asyncio.to_thread(validate_integration_configuration_no_ssrf, config)
    options = KafkaAdapter(config).connection_options(credentials, timeout_seconds=10)
    connection = await _connect(config, options)
    if connection is None:
        fail_publish("kafka_connection_failed", retryable=True)
    try:
        metadata = await connection.send(NonCreatingMetadataRequest(topic))
        for broker in metadata.brokers:
            await approved_broker_addresses(broker[1], broker[2])
        # Metadata response tuples share their error/topic prefix across v4/v5.
        for item in metadata.topics:
            if item[1] != topic:
                continue
            if item[0] == UnknownTopicOrPartitionError.errno:
                # Confirm absence in a complete topic listing; a transient
                # UnknownTopicOrPartition response alone is not definitive.
                listing = await connection.send(MetadataRequest(topics=None, allow_auto_topic_creation=False))
                if not any(row[1] == topic for row in listing.topics):
                    fail_publish("kafka_topic_not_found")
                fail_publish("kafka_metadata_unavailable", retryable=True)
            if item[0]:
                error_type = for_code(item[0])
                raise error_type
            return
        fail_publish("kafka_metadata_unavailable", retryable=True)
    finally:
        await _close(connection)


@activity.defn(name=ActivityName.KAFKA_PUBLISH_PREPARE)
async def prepare_kafka_publish(
    parameters: dict[str, Any], project_id: str, timeout_seconds: float = 30
) -> dict[str, Any]:
    """Resolve secrets once per logical invocation; Temporal encrypts this result."""
    try:
        async with asyncio.timeout(timeout_seconds):
            model = KafkaPublishParameters.model_validate(parameters)
            async with _session_factory() as session:
                config, revision = await current_publish_resources(session, model, project_id)
                credentials: dict[str, Any] = {"extra_vars": {}, "_secret_values": []}
                if model.credential_id is not None:
                    credentials = await _resolve_single_credential(
                        session, create_secret_service(session), "kafka_publish", model.credential_id, project_id
                    )
            await check_publish_topic(config, credentials["extra_vars"], model.topic)
            prepared = {
                **parameters,
                "_resolved_credentials": credentials,
                "_resolved_integration": config.model_dump(mode="json"),
                "_kafka_revision": revision,
            }
            if temporal_argument_size([prepared]) > TEMPORAL_PAYLOAD_MAX_BYTES:
                fail_publish("kafka_arguments_too_large")
            return prepared
    except ApplicationError as exc:
        if (exc.type or "").startswith("kafka_"):
            raise
        fail_publish("kafka_invalid_reference", retryable=not exc.non_retryable)
    except OperationalError:
        fail_publish("kafka_connection_failed", retryable=True)
    except (ValueError, TypeError):
        fail_publish("kafka_invalid_message")
    except Exception as exc:  # noqa: BLE001 - sanitize unknown SDK/driver errors without exposing their contents
        code, retryable, _fatal = classify_publish_error(exc)
        error = publish_failure(code, retryable=retryable)
        raise error from None
