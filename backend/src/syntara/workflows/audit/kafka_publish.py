"""Audit confirmed Kafka Publish deliveries through the platform outbox."""

from dataclasses import dataclass
from uuid import UUID, uuid5

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventStatus
from syntara.audit.models.structured_data import AuditContextData


@dataclass(frozen=True)
class KafkaPublishAcknowledgedEvent:
    """A Publish activity whose successful completion confirms Kafka acknowledgement."""

    workflow_id: UUID
    execution_id: UUID
    activity_execution_id: UUID
    activity_id: str
    execution_principal_id: UUID


class KafkaPublishAcknowledgedHandler(AuditEventHandler[KafkaPublishAcknowledgedEvent]):
    """Audit the acknowledgement with workflow and activity identifiers."""

    def handle(self, event: KafkaPublishAcknowledgedEvent) -> AuditEvent:
        """Describe the action without copying its inputs or result data."""
        return AuditEvent(
            event_id=uuid5(event.activity_execution_id, "kafka_publish_acknowledged"),
            event_category=EventCategory.WORKFLOW_EVENT,
            event_status=EventStatus.SUCCESS,
            event_action="kafka_publish_acknowledged",
            event_message="Kafka acknowledged the publish action",
            source_component="syntara.workflows.kafka_publish",
            resource_urn=f"urn:syntara:activity-execution:{event.activity_execution_id}",
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            activity_id=event.activity_id,
            actor_id=event.execution_principal_id,
            structured_data=AuditContextData(
                data_type="kafka-publish-acknowledged",
                activity_execution_id=str(event.activity_execution_id),
            ),
        )
