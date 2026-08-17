# Resilient Background Execution

Syntara originally processed system operations — document conversion, agent execution — inside
FastAPI `BackgroundTasks`. These are fire-and-forget callbacks that run in the same process as the
HTTP request that triggered them: no retry, no durability, no visibility, and critically, they share
a single-process execution slot with user workflows. A burst of file uploads could saturate the
worker pool and stall every user-initiated workflow run until the backlog cleared.

This document describes the architecture built to fix that: a dedicated Temporal task queue and
worker for built-in workflows, with CPU-based horizontal autoscaling, Prometheus observability,
and operator-managed lifecycle from a single CRD field.

## The Problem in Detail

FastAPI's `BackgroundTasks` runs callbacks in the request's lifespan context — the same thread
pool that handles HTTP requests. The failure modes were:

- **No retry**: a transient Temporal connection error or database blip silently drops the job.
- **No durability**: process restart during a document conversion means the conversion never
  completes and the caller gets no signal.
- **No queue isolation**: bulk file uploads generating many conversions could fill the Temporal
  worker's activity pool, delaying user-initiated workflows waiting for the same pool.
- **No observability**: no queue depth metric, no way to know how many system jobs were
  queued or in-flight, no Prometheus gauge to alert on.

The fix is to replace `BackgroundTasks` usage with built-in Temporal workflows that run on their
own dedicated queue, served by their own dedicated worker deployment.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Syntara API (FastAPI)                                                        │
│                                                                             │
│  POST /executions  →  ExecutionService.start_workflow(is_builtin=False)    │
│       ↓ task_queue = orchestrator-workflow-queue                                   │
│                                                                             │
│  Built-in trigger  →  ExecutionService.start_workflow(is_builtin=True)     │
│       ↓ task_queue = orchestrator-background-queue                                 │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
              ┌────────────▼─────────────┐
              │   Temporal Server        │
              │  (NUM_HISTORY_SHARDS=512)│
              │                          │
              │  orchestrator-workflow-queue    ◄──── orchestrator-workflow-worker pod(s)
              │  orchestrator-background-queue  ◄──── orchestrator-background-worker pod(s) ← HPA
              └──────────────────────────┘
```

The API server determines the queue at dispatch time by reading `is_builtin` from the `Workflow`
database row (see [Built-in Workflow Routing](#built-in-workflow-routing)). Once dispatched, the
Temporal server's own queue isolation guarantees that a spike on `orchestrator-background-queue` never
touches `orchestrator-workflow-queue` and vice versa.

## Built-in Workflow Routing

### The `is_builtin` Flag

`Workflow.is_builtin` (`src/syntara/workflows/models/workflow.py`) is a boolean column on the
`Workflow` database table, defaulting `false` and indexed for fast queue-routing lookups:

```python
is_builtin: bool = Field(
    default=False,
    index=True,
    sa_column_kwargs={"server_default": text("false")},
)
```

Built-in workflows (Document Conversion, Agent Execution) are seeded into the database by
`seed_builtin_workflows()` (`src/syntara/workflows/seed_builtin.py`) with `is_builtin=True`. The
seeder is idempotent — re-running it updates the workflow definition if it changed, and is a
no-op if nothing changed. It runs at startup, so the database always reflects the latest
built-in workflow definition without manual intervention.

### Routing at Dispatch Time

`TemporalExecutionService.start_workflow()` (`src/syntara/workflows/workflow_engine/services/temporal_execution_service.py`)
accepts an `is_builtin: bool = False` keyword argument. The queue selection is a single
conditional at the Temporal client call:

```python
handle = await self.temporal_client.start_workflow(
    OrchestratorWorkflow.run,
    args=[...],
    id=temporal_workflow_id,
    task_queue=self.background_task_queue if is_builtin else self.task_queue,
)
```

`self.background_task_queue` defaults to `orchestrator-background-queue` (constant
`TEMPORAL_DEFAULT_BACKGROUND_TASK_QUEUE` in `src/syntara/core/config/base.py`) but is
overridable via the `APP_BACKGROUND_TASK_QUEUE` environment variable. `create_temporal_execution_service()`
reads both queue names from settings and wires them into the service at construction time, so
nothing downstream of the service needs to know about queue names.

### Configuration

| Setting | Env var | Default |
|---|---|---|
| `task_queue` | `APP_TASK_QUEUE` | `orchestrator-workflow-queue` |
| `background_task_queue` | `APP_BACKGROUND_TASK_QUEUE` | `orchestrator-background-queue` |
| `metrics_worker_port` | `APP_METRICS_WORKER_PORT` | `9090` |

## The Background Worker

### Entrypoint and Lifecycle

`src/syntara/workflows/background_worker.py` is the background worker process entrypoint:

```
python -m syntara.workflows.background_worker
```

It calls the same `run_worker()` lifecycle function as the main workflow worker
(`src/syntara/workflows/worker_lifecycle.py`). `run_worker()` is not a background task or
a thread — it is the main event loop of the worker process, blocking on
`asyncio.Event.wait()` until a `SIGTERM` or `SIGINT` arrives, then draining in-flight
activities before exit.

The shared `run_worker()` function handles:

1. Signal registration (`SIGTERM` / `SIGINT` → graceful drain).
2. `SettingsCache` initialization for runtime-configurable settings (log level, telemetry key).
3. **Prometheus metrics server startup** on `settings.metrics_worker_port` (port 9090). This
   is a daemon thread started before the Temporal connection, so a metrics scrape works even
   during Temporal outages. Port-binding failures are logged as warnings and ignored — a
   missing metrics endpoint must never prevent the worker from starting.
4. `discover_and_register_all_handlers()` for audit event watchers.
5. Calling the caller-supplied `start_fn()` to connect to Temporal and begin polling.

### Reduced Activity Surface

The background worker runs a smaller activity registry than the main workflow worker
(`src/syntara/workflows/workflow_engine/activities/registry.py`):

| Registry | Used by | Activities |
|---|---|---|
| `ACTIVITY_REGISTRY` | `orchestrator-workflow-worker` | All ~24 activities (HTTP, script, agentic, AAP, approvals, triggers, …) |
| `BACKGROUND_ACTIVITY_REGISTRY` | `orchestrator-background-worker` | `register_activity_monitoring`, `fetch_workflow_runtime_settings`, `manual_trigger`, `execute_internal_activity` |

This is not just an optimisation — it is a security boundary. The background worker cannot
execute user-facing activities (HTTP requests, scripts, AAP jobs) even if someone managed to
route a workflow to `orchestrator-background-queue`. Built-in workflows use `execute_internal_activity`
which dispatches only to pre-registered internal handlers, not arbitrary user code.

## Observability

### Prometheus Metrics Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│  Prometheus                                                               │
│    scrapes: /metrics every 30s                                            │
│                                                                           │
│  ┌─────────────────┐  ServiceMonitor  ┌────────────────────────────────┐  │
│  │ <cr>-backend    │◄────────────────│ <cr>-backend ServiceMonitor    │  │
│  │   port: https   │   HTTPS + mTLS  │   scheme: https, port: https   │  │
│  └─────────────────┘                 └────────────────────────────────┘  │
│                                                                           │
│  ┌─────────────────┐  ServiceMonitor  ┌────────────────────────────────┐  │
│  │ <cr>-worker-    │◄────────────────│ <cr>-worker ServiceMonitor     │  │
│  │ metrics svc     │   HTTP          │   scheme: http, port: metrics  │  │
│  │   port: 9090    │                 └────────────────────────────────┘  │
│  └─────────────────┘                                                     │
│           ↑ selector: component=worker                                    │
│    ┌──────┴───────┐                                                       │
│    │ worker pods  │  (no existing Service; metrics Service is dedicated)  │
│    └──────────────┘                                                       │
│                                                                           │
│  (same pattern for background-worker and temporal-server)                 │
└───────────────────────────────────────────────────────────────────────────┘
```

### ServiceMonitors

`reconcileServiceMonitors()` (`internal/controller/service_monitors.go`) creates four
ServiceMonitor objects in the app namespace on every reconcile:

| Component | Port | Scheme | Notes |
|---|---|---|---|
| `<cr>-backend` | `https` (8000) | HTTPS | Uses operator-managed or customer-provided CA |
| `<cr>-worker` | `metrics` (9090) | HTTP | Targets dedicated metrics Service |
| `<cr>-background-worker` | `metrics` (9090) | HTTP | Targets dedicated metrics Service |
| `<cr>-temporal-server` | `metrics` (9090) | HTTP | Temporal built-in Prometheus endpoint |

ServiceMonitors are built as `*unstructured.Unstructured` objects rather than typed
`monitoringv1.ServiceMonitor` structs. This avoids adding
`github.com/prometheus-operator/prometheus-operator` as a Go module dependency — the operator
only needs to manage the resource via SSA, not import the entire Prometheus Operator SDK. The
GVK is `monitoring.coreos.com/v1/ServiceMonitor`.

The operator checks for the ServiceMonitor CRD at startup via the manager's REST mapper:

```go
func (r *...) isMonitoringAPIAvailable(mgr ctrl.Manager) bool {
    _, err := mgr.GetRESTMapper().RESTMapping(serviceMonitorGVK.GroupKind(), serviceMonitorGVK.Version)
    return err == nil
}
```

If the CRD is absent (Prometheus Operator not installed), `reconcileServiceMonitors()` is a
no-op — the operator degrades gracefully. The result is stored as `r.monitoringAPIAvailable`
at `SetupWithManager` time so the REST mapper is not called on every reconcile.

### Dedicated Metrics Services for Workers

Workers pull tasks from Temporal — they have no inbound HTTP traffic and therefore no existing
Kubernetes Service. Prometheus's scrape path is `ServiceMonitor → Service → Pod`: without a
Service, the ServiceMonitor has nothing to discover. The operator creates a dedicated
`ClusterIP` metrics Service for each worker (`<cr>-worker-metrics`, `<cr>-background-worker-metrics`):

```
Service: <cr>-worker-metrics
  selector: app.kubernetes.io/component=worker, app.kubernetes.io/instance=<cr>
  port: metrics/9090 → pod port named "metrics"
```

### Worker Prometheus Endpoint

Both worker processes call `prometheus_client.start_http_server(settings.metrics_worker_port)`
inside `run_worker()` before connecting to Temporal. The HTTP server runs in a daemon thread —
it does not participate in the asyncio event loop and does not block startup if the port is
already in use. The port (`9090`, `APP_METRICS_WORKER_PORT`) is the same for both workers
because they run in separate pods; there is no port collision.

The endpoint exposes standard `prometheus_client` default collectors (GC stats, process metrics)
plus any application-level gauges registered against the default registry.

### Backend ServiceMonitor: mTLS

The backend FastAPI app serves `/metrics` over HTTPS on port 8000 alongside its API traffic.
The ServiceMonitor's `tlsConfig` references the CA certificate from the operator-managed
internal CA Secret (`<cr>-internal-ca`) unless the CR has `spec.tls.caSecretRef` set, in which
case the customer-provided CA is used. This mirrors the same CA selection logic used in
`tlsCAVolume()` for pod certificate mounting — both agree on the same source.

### Temporal Server Prometheus Endpoint

Temporal exposes its own Prometheus metrics at `:9090/metrics` via:

```yaml
# temporal-config.yaml.tmpl (rendered into <cr>-temporal-config ConfigMap)
global:
  metrics:
    prometheus:
      listenAddress: "0.0.0.0:9090"
```

The Temporal Service's existing `metrics` port (named `metrics`, port 9090) carries this
traffic. The `<cr>-temporal-server` ServiceMonitor targets this Service port directly — no
dedicated metrics Service is needed because Temporal's Service already exists.

### Queue Depth Metric

`src/syntara/metrics/queue_depth_poller.py` runs as a `PeriodicWorker` inside the API server
process, polling Temporal's `DescribeTaskQueue` RPC every 5 seconds for both queues:

```python
task_queues = list(dict.fromkeys([settings.task_queue, settings.background_task_queue]))
```

Each poll emits a `TEMPORAL_QUEUE_DEPTH` gauge record labelled with the queue name:

```python
recorder.record(
    MetricType.TEMPORAL_QUEUE_DEPTH,
    float(depth),
    labels={"task_queue": task_queue},  # "orchestrator-workflow-queue" or "orchestrator-background-queue"
)
```

This produces two Prometheus time series from the same metric name, distinguished only by the
`task_queue` label. A Prometheus query for the background queue depth:

```promql
temporal_queue_depth{task_queue="orchestrator-background-queue"}
```

This label is what makes it possible to configure HPA rules targeting specifically the background
queue's backlog count rather than the aggregate depth of both queues combined.

The poller uses `coordinate=False` so that every API server replica independently polls
Temporal. Prometheus aggregates across replicas at scrape time; they should all see the same
queue depth, and any disagreement averages out.

## How to Verify Everything is Working

### Verify Worker Metrics Endpoints

```bash
# Port-forward to a background worker pod and scrape its metrics:
kubectl port-forward -n <namespace> \
  $(kubectl get pod -n <namespace> -l app.kubernetes.io/component=background-worker \
    -o jsonpath='{.items[0].metadata.name}') 9090:9090
curl http://localhost:9090/metrics
```

Expected: Prometheus text format with `# HELP python_gc_objects_collected_total` and similar
standard Python process metrics.

### Verify Queue Depth Metrics are Flowing

If Prometheus is configured to scrape the backend service:

```promql
# Both series should be present (value may be 0 when queues are idle)
orchestrator_temporal_queue_depth{task_queue="orchestrator-workflow-queue"}
orchestrator_temporal_queue_depth{task_queue="orchestrator-background-queue"}
```

From the API server's internal metrics endpoint:

```bash
curl -k https://<backend-svc>/api/v1/internal/metrics | jq '.queue_depth'
```

### Verify Built-in Workflow Routes to Background Queue

Start a document conversion and observe the background worker's Temporal task count rising while
the main worker remains idle. Alternatively, query the Temporal UI:

- Navigate to the Temporal UI (`http://<cluster>:8081`)
- Select namespace `default`
- Filter by Task Queue `orchestrator-background-queue`
- A running document conversion should appear here, not under `orchestrator-workflow-queue`

## Adding a New Built-in Workflow

A built-in workflow is a system operation that runs on `orchestrator-background-queue`, is seeded
automatically at startup, and is hidden from regular users. Adding one requires changes in two
files only.

### Step 1 — Register an internal operation handler

`execute_internal_activity` (`src/syntara/workflows/workflow_engine/activities/internal_activity.py`)
is the single Temporal activity that all built-in workflows dispatch through. It looks up the
`activity` parameter from the node config in `_DISPATCH`, a plain dict of
`str → async callable`:

```python
_DISPATCH: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "document_conversion": _run_document_conversion,
    "invocation_execution": _run_invocation_execution,
    # your new handler here
}
```

Add a handler function and register it:

```python
async def _run_my_operation(operation_input: dict[str, Any]) -> dict[str, Any]:
    resource_id = operation_input.get("resource_id")
    if not resource_id:
        raise ApplicationError("my_operation requires 'resource_id'", non_retryable=True)

    # Heavy imports go here (lazy, inside the function) to avoid Temporal sandbox warnings
    from syntara.my_domain.tasks import MyTask  # noqa: PLC0415

    result = await MyTask().run(UUID(resource_id))
    return {"output": {"status": result.name}}

_DISPATCH = {
    ...,
    "my_operation": _run_my_operation,
}
```

Two conventions to follow:
- **Lazy imports** — import heavy dependencies inside the handler, not at module level. Eager
  imports trigger Temporal sandbox warnings that can affect other activities.
- **`non_retryable=True` on validation errors** — if the input is structurally wrong (missing
  required field, invalid UUID), the workflow should fail fast, not retry. Use
  `non_retryable=False` for transient failures (network, DB) where retry is meaningful.

### Step 2 — Add the workflow definition to the seed

`_BUILTIN_DEFINITIONS` (`src/syntara/workflows/seed_builtin.py`) is a list of V2 workflow
definition dicts. Add an entry:

```python
{
    "schema_version": "2.0.0",
    "name": "My Operation",            # unique, user-visible name
    "description": "...",
    "triggers": [
        {"id": "trigger_api", "type": "manual_trigger", "parameters": {}}
    ],
    "nodes": [
        {
            "id": "run",
            "type": "internal_activity",
            "name": "Run My Operation",
            "parameters": {
                "activity": "my_operation",               # must match _DISPATCH key
                "input": {"resource_id": "${trigger.resource_id}"},
            },
            "settings": {
                "timeout": 300,                            # per-attempt seconds
                "retry_policy": {
                    "max_retries": 2,
                    "initial_interval": 5,
                    "backoff_coefficient": 2.0,
                },
            },
        }
    ],
    "edges": [{"from": "trigger_api", "to": "run"}],
}
```

**Timeout sizing**: `timeout` is a per-attempt `start_to_close_timeout`. With retries, the
worst-case total wall-clock is `timeout × (max_retries + 1) + sum(backoff intervals)`. Keep
this below your schedule interval if the workflow is scheduled, or below any caller-side SLA
if triggered on-demand.

The seeder (`seed_builtin_workflows`) is idempotent — re-running it creates the workflow on
first boot and bumps the version automatically if the definition changes. No migration is
needed. The workflow is stored with `is_builtin=True`, hidden from regular users by default,
and not deletable via the API.

### What you do not need to change

- **`BACKGROUND_ACTIVITY_REGISTRY`** — `execute_internal_activity` is already registered
  there. Adding a new dispatch key in `_DISPATCH` is enough; no Temporal activity registration
  is needed.
- **`ACTIVITY_REGISTRY`** — `execute_internal_activity` is also registered in the main worker
  registry. Built-in workflows can run on either worker, but will be routed to
  `orchestrator-background-queue` when dispatched with `is_builtin=True`.
- **`is_builtin` routing** — callers pass `is_builtin=True` to
  `TemporalExecutionService.start_workflow()`. The seeder marks the `Workflow` row with
  `is_builtin=True` automatically.
- **Kubernetes** — no operator changes are needed. The background worker Deployment and HPA
  already exist and pick up work from the queue immediately.

### Triggering the new workflow

Built-in workflows are triggered programmatically, not by users. Pass the workflow name and
`is_builtin=True` to the execution service from wherever the operation is initiated:

```python
await execution_service.start_workflow(
    workflow_def=workflow_version.workflow_definition,
    workflow_name="My Operation",
    trigger_node_id="trigger_api",
    input_data={"resource_id": str(resource_id)},
    is_builtin=True,
)
```

The service looks up `background_task_queue` from settings and routes the Temporal workflow
there. From this point, execution is identical to any other workflow — visible in the Temporal
UI under `orchestrator-background-queue`, status synced to the DB via `ActivitySyncService`, and
surfaced in the Syntara UI for administrators with the builtin toggle enabled.

## Constraints and Known Gaps

**OOM under sustained LLM load**: The background worker executes memory-heavy LLM/agent activities
(Document Conversion, Agent Execution). Under sustained load, uncapped activity concurrency can cause
out-of-memory pod restarts. The fix involves two coordinated changes:

1. **Activity concurrency cap**: `APP_BACKGROUND_WORKER_MAX_CONCURRENT_ACTIVITIES` (default: 10)
   controls the maximum concurrent Temporal activities per pod. This is the primary knob. LLM activities
   consume ~200-500MB each; 10 concurrent activities fit within a 1Gi pod budget.

   **Behavior when cap is reached**: Activities do not fail when the concurrency limit is reached. Instead,
   incoming activity tasks queue in the Temporal task queue until a worker slot becomes available. The
   worker polls the queue and processes tasks in FIFO order. This is standard Temporal behavior — the queue
   acts as a backpressure mechanism. If demand consistently exceeds per-pod capacity (10 activities), the
   Kubernetes HPA scales the background worker deployment horizontally by adding replicas, distributing
   load across multiple pods. This allows the system to handle arbitrarily high sustained load.

2. **Pod memory limit**: Kubernetes pod memory limit should be **1Gi minimum** for background workers
   (configured in the operator via `spec.backgroundWorker.resources.limits.memory`). The previous
   512Mi default was insufficient even with concurrency capping.

Note: `max_cached_workflows` (default: 1000) caps workflow history caching in Temporal SDK, not activity
concurrency. These are separate tuning knobs — do not confuse them when diagnosing OOM. For high activity
concurrency load, tune `APP_BACKGROUND_WORKER_MAX_CONCURRENT_ACTIVITIES`, not `max_cached_workflows`.

**No CPU-independent HPA metric**: the HPA scales on CPU utilization. This works for CPU-bound
activities but is a weak proxy for queue backlog depth. A better HPA trigger would be the
`orchestrator_temporal_queue_depth{task_queue="orchestrator-background-queue"}` Prometheus metric via a
custom metrics adapter (e.g. Prometheus Adapter or KEDA). The current setup is safe and
correct; the CPU trigger just responds to load with some lag rather than immediately to queue depth.

## Related Documentation

- [Workflow Engine Architecture](workflow-engine/workflow-engine-overview.md) — how `OrchestratorWorkflow` executes both user and built-in workflows identically
- [Execution Runtime](execution-runtime.md) — `POST /executions` API, two-phase creation, live status
- [Observability Standards](standards/observability.md) — `MetricsRecorder` usage, Prometheus gauge patterns
- [Configuration Standards](standards/configuration.md) — adding new settings, Pydantic Settings patterns
