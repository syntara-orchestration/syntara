"""Preconditions for removing the legacy event delivery and runtime tables."""

from sqlalchemy import Connection, text


def require_resolved_eventstream_ledger(connection: Connection) -> None:
    """Refuse removal while legacy workers or irreplaceable delivery/lifecycle evidence remain."""
    checks = (
        (
            "Stop all event workers before upgrading",
            "SELECT EXISTS (SELECT 1 FROM event_consumer_workers WHERE heartbeat_until > clock_timestamp())",
        ),
        (
            "Drain legacy subscription runtimes before upgrading",
            "SELECT EXISTS (SELECT 1 FROM event_subscription_runtimes WHERE NOT stopped OR permanent_content_error)",
        ),
        (
            "Resolve legacy deliveries before upgrading",
            "SELECT EXISTS (SELECT 1 FROM event_deliveries WHERE state <> 'scheduled')",
        ),
        (
            "Preserve legacy source retirement evidence before upgrading",
            "SELECT EXISTS (SELECT 1 FROM event_subscription_sources "
            "WHERE retirement_authorized_by IS NOT NULL OR retirement_reason IS NOT NULL "
            "OR retirement_completed_at IS NOT NULL)",
        ),
        (
            "Complete pending Kafka position recovery before upgrading",
            "SELECT EXISTS (SELECT 1 FROM kafka_partition_initial_positions WHERE recovery_token IS NOT NULL)",
        ),
        (
            "Restore source initialization history before upgrading",
            "SELECT EXISTS (SELECT 1 FROM event_subscription_sources WHERE delivery_evidence_revision > 0 "
            "AND initialized_at IS NULL AND NULLIF(configuration->'initial_partition_ids', 'null'::jsonb) IS NULL)",
        ),
        (
            "Resolve unconfirmed legacy event Executions before upgrading",
            "SELECT EXISTS (SELECT 1 FROM executions WHERE execution_metadata ? 'event_delivery' "
            "AND execution_metadata->'event_delivery'->>'scheduling_state' IS DISTINCT FROM 'confirmed')",
        ),
        (
            "Restore confirmed normal Executions before removing accepted delivery evidence",
            "SELECT EXISTS (SELECT 1 FROM event_deliveries AS delivery WHERE delivery.state = 'scheduled' "
            "AND NOT EXISTS (SELECT 1 FROM executions AS execution WHERE execution.id = delivery.execution_identity "
            "AND execution.workflow_id = delivery.workflow_id "
            "AND execution.temporal_workflow_id = delivery.temporal_workflow_id "
            "AND execution.workflow_version_id::text = delivery.frozen_binding->>'workflow_version_id' "
            "AND execution.created_by::text = delivery.frozen_binding->>'execution_principal_id' "
            "AND execution.execution_metadata->'event_delivery'->>'scheduling_state' = 'confirmed' "
            "AND execution.execution_metadata->'event_delivery'->>'identity_digest' = delivery.identity_digest "
            "AND execution.execution_metadata->'event_delivery'->>'temporal_run_id' = delivery.temporal_run_id "
            "AND execution.execution_metadata->'event_delivery'->>'input_fingerprint' "
            "= delivery.frozen_binding->>'input_fingerprint'))",
        ),
    )
    for message, statement in checks:
        if connection.scalar(text(statement)):
            raise RuntimeError(message)
