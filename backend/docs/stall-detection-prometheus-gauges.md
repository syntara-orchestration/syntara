# Stall Detection Prometheus Gauge Design

## Metrics

The stall detection worker updates three Prometheus metrics (SDP R23/AC-13):
- `orchestrator_stalled_workflows_current` (gauge)
- `orchestrator_stalled_steps_current` (gauge)
- `orchestrator_stalled_workflows_total` (counter)

## Uncoordinated Design (`coordinate=False`)

Every replica runs the stall detection callback independently. This is safe because:

1. **Activity claims are atomic**: `UPDATE ... RETURNING` with a `stall_alert_at IS NULL` guard ensures each activity is claimed exactly once, even under concurrent replicas.
2. **Gauges are database-derived absolutes**: Each replica queries the database for current counts and sets its gauges to the same values. No increments, no double-counting.
3. **Counters use atomic deduplication**: `first_stall_detected_at` is set via `UPDATE ... WHERE first_stall_detected_at IS NULL ... RETURNING`, so only one replica increments the counter per execution.

This matches the existing queue-depth poller pattern and eliminates the stale-gauge problem that occurred with the previous coordinated-scanner design (where leadership transfers left non-leader replicas with stale or zero gauge values).

## Prometheus Configuration

Every replica refreshes gauges from the database, so all replicas report the same absolute values. Query a single replica's gauge directly, or use `max()` across replicas to produce a cluster-wide value:

```promql
max(orchestrator_stalled_workflows_current) by (cluster)
max(orchestrator_stalled_steps_current) by (cluster)
```

**Do not use `sum()` across replicas** — each replica reports the full count, so summing would overcount by a factor of the replica count.
