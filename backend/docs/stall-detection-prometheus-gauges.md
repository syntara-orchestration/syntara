# Stall Detection Prometheus Gauge Deployment Requirements

## Current Implementation

The stall detection worker updates three Prometheus metrics (SDP R23/AC-13):
- `orchestrator_stalled_workflows_current` (gauge)
- `orchestrator_stalled_steps_current` (gauge)
- `orchestrator_stalled_workflows_total` (counter)

**Coordinated Scanner:** Only the process holding the PostgreSQL advisory lock (via `PeriodicWorker(coordinate=True)`) executes the stall detection callback and updates the gauge values. Non-leader replicas never execute the callback.

## Known Limitation: Stale Gauge Values

When leadership transfers between replicas (e.g., due to scale-down, restart, or lock timeout), the **previous leader retains its last gauge values** until:
1. It regains the lock and updates them, OR
2. The process restarts (gauges reset to 0)

This creates incorrect scrape results depending on the aggregation method:

| Scrape Config | Problem |
|---|---|
| `sum()` across all replicas | **Overcounts** - includes stale values from old leaders |
| `max()` across all replicas | **Shows stale highs** - doesn't reflect decreases when new leader has lower counts |
| Single target (static pod) | **Breaks on pod restart** - scrape target becomes unavailable |

## Required Deployment Configuration

Until the codebase provides leader-aware gauge zeroing (see "Future Enhancement" below), deployments **must** use one of these approaches:

### Option 1: Scrape All Replicas with Leader Filtering (Recommended)

Add a `stall_detection_is_leader` gauge that tracks lock ownership:
- Leader sets to `1.0` after acquiring lock
- Non-leaders set to `0.0`
- Prometheus filters with `stall_detection_is_leader == 1`

**Status:** NOT IMPLEMENTED - requires code change in `PeriodicWorker` or stall detection worker.

### Option 2: Accept Stale Values with max() Aggregation

Use `max()` aggregation and accept that gauge values may be stale high for one scrape interval after leadership transfer.

**Acceptable when:**
- Stall counts typically increase (rare decreases)
- Alerting thresholds have sufficient margin
- Scrape interval is short relative to lock duration

**Prometheus query:**
```promql
max(orchestrator_stalled_workflows_current) by (cluster)
max(orchestrator_stalled_steps_current) by (cluster)
```

**Risk:** False-positive alerts if stall count drops significantly during leadership transfer.

### Option 3: Scrape Only the Current Leader (Manual)

Manually update scrape config to target the current leader pod.

**Not recommended** - requires manual intervention on every leadership transfer.

## Future Enhancement: Leader-Aware Gauge Zeroing

To eliminate stale values, the worker needs to:
1. Set a `stall_detection_is_leader` gauge to `1.0` when acquiring the lock
2. Set it to `0.0` and zero all stall gauges when:
   - Losing the lock (currently not detectable in `PeriodicWorker`)
   - On worker shutdown

This requires either:
- Adding a "lost lock" callback to `PeriodicWorker`, OR
- Checking lock ownership before every Prometheus scrape (expensive), OR
- A separate heartbeat mechanism that zeros gauges if the lock heartbeat expires

**Decision needed:** Which approach to implement, or whether to accept the limitation with Option 2 above.

## Impact on AAP-92825

The AAP-92825 PR preserves the coordinated-scanner-only design and documents this limitation. The PR does **not** implement leader-aware gauge zeroing, as that would require changes to `PeriodicWorker` or a new heartbeat mechanism - both outside the scope of this review thread.

**Reviewer action required:** Confirm whether Option 2 (max aggregation with stale-value risk) is acceptable, or whether leader-aware gauge zeroing must be implemented before merging.
