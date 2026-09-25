# Execution Plane: Work Store

`WorkStore` is the internal Python interface for interacting with `WorkItem` records in its durable
store (Postgres in the current branch).
See [logical_components.md](logical_components.md) for how it fits into the logical decomposition of the Execution Plane service.

**Source:** `execution_plane/work_store.py`, `execution_plane/models/work_item.py`

---

## Context

*(Implemented)*

The Consumer (Syntara or AWX) submits work to the [Work Executor](work-executor.md),
which persists a `WorkItem` to the `WorkStore` in `PENDING` status. The `WorkStore`
has durable Postgres storage — a `WorkItem` written there survives process restarts and
worker crashes.

From that point, multiple other [logical components](logical_components.md) interact with the `WorkStore` through its
public methods:

| Component | Operation |
|---|---|
| [Work Executor](work-executor.md) | Creates the initial `WorkItem` record |
| [Work Scheduler](work-scheduler.md) | `claim_one()` — atomically moves one item from `PENDING` to `CLAIMED` |
| Work Watcher | `set_result()` — writes result and transitions to `COMPLETED` or `FAILED` |
| [Work Scheduler](work-scheduler.md) | Records placement failure timestamp to prevent thrashing *(not yet implemented)* |
| Completion Notifier | Reads terminal items with undelivered callbacks |
| Startup recovery | `find_undelivered()` — finds terminal items with `NULL signaled_at` |
| Completion Notifier | `mark_signal_delivered()` — sets `signaled_at` after the callback is confirmed |

---

## Work item lifecycle

```
PENDING → CLAIMED → RUNNING → COMPLETED
                           → FAILED
```

| Status / phase | Meaning |
|---|---|
| `PENDING` | Submitted, waiting to be claimed by a worker |
| `CLAIMED` | Locked by one worker; Work Scheduler is resolving an `ExecutionTarget` and a `WorkerManager` is being instantiated for it |
| *(transmitting)* | `ExecutionTarget` set on the `WorkItem`; capacity claimed in the local `ExecutionTargetStore`; work dispatched to infrastructure. Not a recorded status — see [worker-manager.md §Capacity management](worker-manager.md#capacity-management) |
| `RUNNING` | Work executing in the worker pool |
| `COMPLETED` | Finished successfully; result stored; Target capacity freed |
| `FAILED` | Execution error; error detail stored; Target capacity freed |

The capacity claim made during the transmitting phase is held for the life of the job.
When the completion callback fires — on `COMPLETED` or `FAILED` — the [Worker Manager](worker-manager.md)
decrements the Target's in-flight count in the `ExecutionTargetStore`. For Targets with a
fixed `pool_size`, this is the backpressure mechanism: no new work is dispatched to a
Target whose `current_jobs` has reached `pool_size`.

---

## Public methods

*(Implemented)*

| Method | Description |
|---|---|
| `claim_one()` | Atomically claims one `PENDING` item (`SELECT FOR UPDATE SKIP LOCKED`) |
| `set_result(item, result, status)` | Writes result dict and transitions status |
| `mark_signal_delivered(item)` | Sets `signaled_at` after Temporal callback confirmed — called by the Completion Notifier once it has fired the callback. Output collection is the Work Watcher's responsibility; how it handles large or streamed output is not yet designed. |
| `find_undelivered()` | Finds terminal items with `NULL signaled_at` for startup recovery |
| `check_ready()` | Health check — verifies DB connectivity and can read work items |
| `requeue_on_placement_failure(item)` | *(Not yet implemented)* Atomically resets status to `PENDING`, nulls the `ExecutionTarget` reference, and sets `last_placement_failed_at` — single UPDATE, no extra round-trip |

---

## Placement failure backoff

*(Not yet implemented)*

When the [Worker Manager](worker-manager.md) fails to place a `WorkItem` on any Target, it records a
`last_placement_failed_at` timestamp on the `WorkItem`. `claim_one()` considers this
timestamp and a configured penalty period: if `now − last_placement_failed_at` is less
than the penalty, the item is skipped. This prevents an unplaceable `WorkItem` from being
retried on every wakeup — pg_notify fires, multiple concurrent EP workers poll, and the
5-second interval all create opportunities for thrashing without this hold-off.

---

## Open areas

- Cancel / revoke path
