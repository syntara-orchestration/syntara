# Execution Plane: Worker Manager

*(Not yet implemented — the Protocol interface is defined; no concrete backend implementation exists.)*

The Worker Manager submits a request to a cluster's API to run a `WorkItem` in an
`ExecutionTarget` — abstractly, a cold or warm worker pool in that cluster. It knows how
to speak the API of each supported cluster type, monitors execution, and persists the
result. Which specific worker within the Target handles the work may become known after
submission, but that is not a constraint.

See [logical_components.md](logical_components.md) for how it fits into the logical decomposition of the Execution Plane service. For K8s-specific implementation see
[kubernetes-backend.md](kubernetes-backend.md).

---

## Interface

Defined as a Protocol in `execution_plane/worker_manager/base.py`. `dispatch` receives a `WorkItem` and an ordered list of candidate `ExecutionTarget`
snapshots (ranked by the `ExecutionTarget` Reconciler). These are static data — not live
model objects — carrying the target's configuration at the time of scheduling:

```python
class WorkerManager(Protocol):
    async def dispatch(self, work_item: WorkItem, targets: list[ExecutionTargetData]) -> dict[str, Any]:
        """Submit work_item to the first viable target and return the terminal result."""
```

`dispatch` works through the list from the front:

1. Consult the `ExecutionTargetStore` for proactive capacity on the first `ExecutionTarget`.
   - **Cold target** — no capacity claim required; proceed directly to submission.
   - **Warm target** — attempt to claim the expected capacity spend in the
     `ExecutionTargetStore`. If the Target is at capacity, move to the next candidate.
2. Bind `execution_target_id` on the `WorkItem` and submit to the cluster's API.
3. On infrastructure rejection, call `WorkStore.requeue_on_placement_failure()` and stop
   — the `WorkItem` re-enters `PENDING` with a hold-off (see Placement failure backoff).

Each backend type (`vanilla_k8s`, `openshell`, …) provides a concrete implementation
that knows how to speak the API of its cluster type.

---

## Submission

To dispatch a `WorkItem`, the Worker Manager reads two records from the database:

- The `ExecutionTarget` record from the `ExecutionTargetStore` — the Target's
  configuration: backend type, label selectors, pool size, and any backend-specific
  fields.
- The `Cluster` record from the `ClusterStore` — the connection details for the cluster
  that hosts this Target: API endpoint, credentials, and namespace.

With those in hand, it calls the API for the cluster's backend type. For the MVP this is
the Kubernetes API: creating or attaching to a pod in the Target's namespace, injecting
the work payload, and monitoring to completion.

Each backend type has its own concrete `WorkerManager` implementation. The `backend_type`
field on the `ExecutionTarget` determines which implementation is used.

---

## Capacity management

The ExecutionTarget Reconciler returns an ordered list of eligible Targets by label matching. The
Worker Manager is responsible for the next layer: ensuring it doesn't over-submit to a
Target and handling K8s-level rejections.

### Proactive

Before submitting, check that the Target has remaining capacity by comparing
`current_jobs` against `pool_size` in Postgres. This is the DB-level atomic selection
described in `pool-reconciler-notes.md`. It is fast, local, and handles concurrent EP
workers correctly without locking across K8s calls.

This check requires that `execution_target_id` is already bound to the `WorkItem` — the
Worker Manager must have selected and recorded a Target (see Target binding below) before
it can look up that Target's capacity.

### Reactive

The Worker Manager submits work to K8s and may receive a rejection (pod unschedulable,
resource pressure, etc.). On bounce-back:

1. Write the rejection timestamp to the `ExecutionTargetStore` for that Target — fire-and-forget,
   no lock held.
2. Subsequent scheduling passes treat a Target that bounced within the backoff window as
   ineligible, even if `current_jobs` says it has headroom.

K8s interaction is slow; no locks are held across it. The proactive DB check runs first
and fast; the reactive update feeds back asynchronously after the K8s call returns.

---

## Target binding and submission failure

*(Not yet implemented)*

Once the Worker Manager selects a Target, it records `execution_target_id` on the
`WorkItem` in the [`WorkStore`](work-store.md). The item is still `CLAIMED` at this point — the bind
happens before the infrastructure call, establishing which Target is responsible.

The Worker Manager then attempts to submit to the Target's infrastructure (e.g. attach
to a warm pod or create a cold-start pod). If that call fails:

1. Call `WorkStore.requeue_on_placement_failure(item)` — a single atomic UPDATE that
   resets the status to `PENDING` and sets `last_placement_failed_at` to now. Both
   happen in the same query, so the timestamp incurs no additional round-trip.
2. The item re-enters the `PENDING` pool but is held off by the penalty period before
   any worker will claim it again.

The `execution_target_id` link is also relevant after a process restart. A `WorkItem`
found in `CLAIMED` or `RUNNING` status on startup was being handled by a known Target —
the EP could query the K8s API for a pod associated with that work ID and, if still
running, skip re-submission and go straight to result collection. Whether to attempt
recovery or fail the item outright is speculative at this point; the exact behaviour
depends on product preference and will only be clear once the full engineering
constraints are known.

---

## Placement failure backoff

*(Not yet implemented)*

When the Worker Manager fails to place a `WorkItem` on any Target, it calls
`WorkStore.requeue_on_placement_failure()`, which resets the `WorkItem` to `PENDING`
and records `last_placement_failed_at` in the [`WorkStore`](work-store.md).
`claim_one()` skips items where `now − last_placement_failed_at` is within the penalty period.

This backoff is what makes the Reactive capacity model coherent and scalable. Without it,
the same unplaceable `WorkItem` is retried on every wakeup by every concurrent EP worker —
pg_notify fires, other workers' poll cycles run, and the 5-second interval ticks — with no
guarantee of spacing. The reactive `ExecutionTargetStore` update (written asynchronously
after the K8s call) cannot suppress those retries on its own; only the per-item hold-off
in the `WorkStore` can.
