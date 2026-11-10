-- Manual maintenance only; never run by setup, migrations or consumer workers.
-- Close admission for this source and externally verify that the exact old
-- process has stopped and cannot resume before supplying worker_fenced=true.
-- Heartbeat/lease expiry alone does not establish that proof.
-- Supply deployment_id, source_id, worker_id and worker_fenced through psql --set.
-- This single statement uses the normal workflow -> subscription -> source
-- lifecycle lock order. It changes only the selected runtime participation.
WITH target AS (
    SELECT CAST(:'deployment_id' AS uuid) AS deployment_id,
           CAST(:'source_id' AS uuid) AS source_id,
           CAST(:'worker_id' AS uuid) AS worker_id,
           CAST(:'worker_fenced' AS boolean) AS worker_fenced
),
locked_workflow AS MATERIALIZED (
    SELECT workflow.id, workflow.is_enabled
    FROM workflows AS workflow
    JOIN event_subscriptions AS subscription ON subscription.workflow_id = workflow.id
    JOIN event_subscription_sources AS source ON source.subscription_id = subscription.id
    CROSS JOIN target
    WHERE source.id = target.source_id
      AND source.deployment_id = target.deployment_id
      AND target.worker_fenced
    FOR UPDATE OF workflow
),
locked_subscription AS MATERIALIZED (
    SELECT subscription.id,
           subscription.desired_enabled,
           subscription.paused,
           subscription.retired,
           subscription.assigned_worker_id,
           subscription.assignment_lease_until,
           workflow.is_enabled AS workflow_enabled
    FROM event_subscriptions AS subscription
    JOIN locked_workflow AS workflow ON workflow.id = subscription.workflow_id
    JOIN event_subscription_sources AS source ON source.subscription_id = subscription.id
    CROSS JOIN target
    WHERE source.id = target.source_id
      AND source.deployment_id = target.deployment_id
    FOR UPDATE OF subscription
),
locked_source AS MATERIALIZED (
    SELECT source.id,
           source.retired_at,
           subscription.desired_enabled,
           subscription.paused,
           subscription.retired,
           subscription.assigned_worker_id,
           subscription.assignment_lease_until,
           subscription.workflow_enabled
    FROM event_subscription_sources AS source
    JOIN locked_subscription AS subscription ON subscription.id = source.subscription_id
    CROSS JOIN target
    WHERE source.id = target.source_id
      AND source.deployment_id = target.deployment_id
    FOR UPDATE OF source
)
UPDATE event_subscription_runtimes AS runtime
SET stopped = true,
    runtime_state = 'stopped',
    applied_revision = NULL,
    applied_published_version_id = NULL
FROM locked_source AS source, target
WHERE runtime.source_id = target.source_id
  AND source.id = target.source_id
  AND runtime.worker_id = CAST(target.worker_id AS text)
  AND NOT runtime.stopped
  AND (
      source.retired_at IS NOT NULL
      OR NOT source.desired_enabled
      OR source.paused
      OR source.retired
      OR NOT source.workflow_enabled
  )
  AND NOT EXISTS (
      SELECT 1
      FROM event_consumer_workers AS worker
      WHERE worker.worker_id = target.worker_id
        AND worker.heartbeat_until > clock_timestamp()
  )
  AND NOT (
      source.assigned_worker_id IS NOT DISTINCT FROM target.worker_id
      AND source.assignment_lease_until > clock_timestamp()
  )
RETURNING runtime.source_id, runtime.worker_id, runtime.stopped, runtime.permanent_content_error;
