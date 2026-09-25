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

Defined as a Protocol in `execution_plane/worker_manager/base.py`. A `WorkerManager`
instance is created by the Work Scheduler for a specific `ExecutionTarget` — it is
configured at instantiation with that Target's data (static snapshot, not a live model
object). `dispatch` then only receives the `WorkItem`:

```python
class WorkerManager(Protocol):
    async def dispatch(self, work_item: WorkItem) -> dict[str, Any]:
        """Submit work_item to this manager's ExecutionTarget and return the terminal result."""
```

The Work Scheduler owns the iteration: it retrieves the ranked list of candidate
`ExecutionTarget`s from the `ExecutionTarget` Reconciler, instantiates a `WorkerManager`
for each one in order, and calls `dispatch`. If `dispatch` fails — capacity exhausted,
infrastructure rejection, or any other error — the Scheduler moves to the next candidate.
If all candidates fail, the `WorkItem` remains `PENDING`.

The `dispatch` signature may grow to accept an `execution_environment` parameter to carry
workload-specific image and mount configuration without a separate configure step; this is
not yet decided.

Each backend type (`vanilla_k8s`, `openshell`, …) provides a concrete implementation
that knows how to speak the API of its cluster type. The `backend_type` field on the
`ExecutionTarget` determines which implementation the Scheduler instantiates.

---

## Hand-off to Work Watcher

The Work Scheduler's scope ends when `dispatch` returns indicating the job has started.
At that point the Scheduler creates a `WorkWatcher` — passing it enough context to locate
and monitor the running job (at minimum the `WorkItem` ID and Target; for K8s, likely
also the pod name or other infrastructure coordinates) — and then moves on to claim and
dispatch more work. The `WorkWatcher` manages the job asynchronously from the Scheduler.

A simple early implementation would use `asyncio.create_task()` per `WorkItem`. Future
implementations may accumulate multiple `WorkItem`s into a single `WorkWatcher` instance
for performance (e.g. batched polling rather than one coroutine per job). The exact
interface between the Scheduler/WorkerManager and the WorkWatcher is not yet designed.

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

The `ExecutionTarget` Reconciler returns a ranked list of eligible Targets. Before the
Work Scheduler calls `dispatch`, it must claim a capacity slot on the chosen Target —
this claim happens *outside* `dispatch` so that the locking mechanism stays separate from
the submission logic and users retain flexibility over how capacity is managed.

The capacity claim mechanism is not yet settled. One option is to use the
`WorkItem`→`ExecutionTarget` reference (see [work-scheduler.md §Capacity management](work-scheduler.md#capacity-management) for the DB-level
locking options), but the exact approach depends on the chosen locking model. What is
clear: some form of lock or atomic reservation must be held before `dispatch` is called,
because dispatching to a Target that is already at capacity wastes an infrastructure call.

### Proactive

Before submitting, check that the Target has remaining capacity by comparing
`current_jobs` against `pool_size` in Postgres. This is the DB-level atomic selection
described in [work-scheduler.md §Capacity management](work-scheduler.md#capacity-management). It is fast, local, and handles concurrent EP
workers correctly without locking across K8s calls.

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
found in `CLAIMED` or `RUNNING` status on startup was being handled by a known Target.
Reattaching to the running pod is not viable — EP will have lost the stdout stream, so
output collected so far is gone. The practical MVP approach is to re-schedule: mark the
`WorkItem` back to `PENDING` and let the Scheduler retry it within its retry count. A pod
that is still running from the previous EP process will complete unobserved and its result
will be lost; for fixed-capacity Targets this also means the old pod's capacity slot must
be released.

The full recovery contract — whether the container entrypoint can signal EP before exiting,
how to avoid double-execution, and how to handle capacity accounting — is a broad open
area and needs its own design work.

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
