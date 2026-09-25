# Execution Plane: Work Scheduler

*(Not yet implemented — a simple poll loop exists in `worker.py`; the full scheduler described here is planned.)*

The Work Scheduler is the core orchestration loop of the Execution Plane. It claims `WorkItem`s from the `WorkStore`, resolves an `ExecutionTarget`, acquires capacity, dispatches to a `WorkerManager`, and hands off to a `WorkWatcher`.

See [logical_components.md](logical_components.md) for how it fits into the logical decomposition of the Execution Plane service. For K8s-specific dispatch details see [kubernetes-backend.md](kubernetes-backend.md).

---

## Responsibility

The Work Scheduler runs a continuous claim-and-dispatch loop:

1. **Claim** — `WorkStore.claim_one()` atomically moves one `WorkItem` from `PENDING` to `CLAIMED`.
2. **Resolve** — the `ExecutionTarget` Reconciler returns an ordered list of eligible `ExecutionTarget`s for the `WorkItem`.
3. **Acquire capacity** — for each candidate in order, attempt to claim a capacity slot (see [Capacity management](#capacity-management)).
4. **Dispatch** — instantiate a `WorkerManager` for the chosen target and call `dispatch(work_item)`.
5. **Hand off** — on successful dispatch, create a `WorkWatcher` for the running job and loop back to claim the next item.
6. **On failure** — if all candidates fail, call `WorkStore.requeue_on_placement_failure(item)` and continue.

---

## Claim loop

The scheduler is woken by two signals:

- `pg_notify` on `execution_plane_work_items` — fired when a new `WorkItem` is inserted, waking the scheduler immediately instead of waiting for the next poll tick.
- A periodic poll interval (5 seconds) — catches any items missed by the notify, and handles startup recovery.

`WorkStore.claim_one()` uses `SELECT FOR UPDATE SKIP LOCKED`. Multiple concurrent EP worker processes race to claim items; only one wins per item. Items with a recent `last_placement_failed_at` are skipped during the penalty period — see [work-store.md §Placement failure backoff](work-store.md#placement-failure-backoff).

---

## Target resolution

The scheduler calls the `ExecutionTarget` Reconciler with a `WorkRequirements` DTO derived from the `WorkItem`. The reconciler returns a `ReconcileResult` with an `available_targets` list of eligible `ExecutionTarget`s — see [executiontarget-reconciler.md](executiontarget-reconciler.md) for selector semantics, lifecycle filtering, and the result structure.

The scheduler iterates `available_targets` in list order, attempting to claim capacity on each in turn until one succeeds.

If `outcome` is `NO_MATCHING_TARGETS`:
- If any ineligible reason is `CAPACITY_EXHAUSTED`, keep the `WorkItem` in `PENDING` — scaling may open capacity.
- Otherwise the `WorkItem` is unschedulable; mark it `FAILED`.

---

## Capacity management

Before calling `dispatch`, the scheduler must claim a capacity slot on the chosen target. This claim happens *outside* `dispatch` so that the locking mechanism stays separate from the submission logic.

Two approaches are viable. The current design uses Option A.

### Option A: DB-level atomic claim (current)

Multiple EP worker processes race to claim capacity directly in Postgres using `SELECT FOR UPDATE SKIP LOCKED`. The DB enforces isolation; no coordination between processes is needed. Releasing capacity on job completion is an unconditional decrement — no lock required, since decrementing an integer counter is safe under concurrency.

`ExecutionTarget` carries two integer fields:

- `pool_size` — configured maximum concurrent jobs for this Target
- `current_jobs` — live count of jobs currently running

Given the ordered list from the reconciler, the scheduler picks the first available Target in a single atomic Postgres query:

```sql
SELECT et.*
FROM execution_targets et
WHERE et.id = ANY($1::uuid[])                    -- reconciler's ordered list of Target IDs
  AND et.current_jobs < et.pool_size             -- has remaining capacity
ORDER BY array_position($1::uuid[], et.id)       -- preserve reconciler's priority order
LIMIT 1
FOR UPDATE SKIP LOCKED
```

`array_position($1, et.id)` orders rows by their position in the input array, so the reconciler's priority ordering is respected exactly. `SKIP LOCKED` means: if another EP worker is currently mid-claim on a Target, skip it and try the next one in priority order — no blocking, no deadlock.

#### Transaction pattern

The full claim is one transaction:

1. Run the query above → row locked
2. `UPDATE execution_targets SET current_jobs = current_jobs + 1 WHERE id = $selected`
3. `UPDATE work_items SET execution_target_id = $selected WHERE id = $work_item`
4. Commit → lock released

On `WorkItem` completion or failure, decrement:

```sql
UPDATE execution_targets SET current_jobs = current_jobs - 1 WHERE id = $selected
```

If the EP worker crashes before commit, the transaction rolls back atomically — `current_jobs` is never incremented and the lock is released. No orphan cleanup needed.

#### Cold-start Targets

For cold-start Targets, `pool_size` is NULL (unlimited). The capacity condition must handle NULL explicitly:

```sql
AND (et.pool_size IS NULL OR et.current_jobs < et.pool_size)
```

`current_jobs` is still tracked for observability even when unconstrained.

#### Edge case: capacity filter races the lock

A Target can pass the capacity filter (`current_jobs < pool_size`) and then lose the lock race to another worker who also passed it. That is correct behaviour — the worker that wins the lock is the one that increments the count. The loser moves on to the next Target in priority order.

### Option B: Singleton capacity manager

A separate in-process service holds all Target capacity state in memory. Any component that needs to subtract capacity asks this service; a thread takes a strong lock scoped to a Target, performs the operation, and releases it. Because only one process is ever allowed to run, lock semantics are simple and flexible — no distributed locking, no DB contention for capacity operations.

Releasing capacity is lock-free: decrementing a counter needs no coordination. This asymmetry (lock to subtract, lock-free to add back) is what makes the singleton viable without a global lock.

**Downsides:** the deployment constraint is strict — exactly one instance must be running at all times. Two instances split state and corrupt counts; zero means capacity checks are unavailable. This requires careful orchestration (leader election or a process supervisor that prevents duplicate instances). Cross-process reliability concerns also apply: a message to the service can be dropped at any point in the call path, and the caller must handle that correctly.

---

## Dispatch and hand-off

Once a capacity slot is claimed, the scheduler instantiates a `WorkerManager` for the chosen `ExecutionTarget` — configured at construction with that Target's data — and calls `dispatch(work_item)`. See [worker-manager.md](worker-manager.md) for the `WorkerManager` interface and submission details.

On successful return from `dispatch`, the scheduler:

1. Creates a `WorkWatcher`, passing it the `WorkItem` ID, Target, and any infrastructure coordinates (e.g. pod name).
2. Returns to claim the next item immediately.

A simple early implementation uses `asyncio.create_task()` per `WorkItem`. Future implementations may accumulate multiple `WorkItem`s into a single `WorkWatcher` for performance (e.g. batched polling). The interface between the Scheduler and the `WorkWatcher` is not yet designed.

The scheduler's scope ends when `dispatch` returns. Output collection, result writing, and completion notification are entirely the `WorkWatcher`'s responsibility.

---

## Placement failure and requeue

*(Not yet implemented)*

If `dispatch` fails on a target, the scheduler moves to the next candidate in the eligible set. If all candidates fail, it calls `WorkStore.requeue_on_placement_failure(item)` — a single atomic UPDATE that resets the `WorkItem` to `PENDING`, nulls the `execution_target_id`, and sets `last_placement_failed_at`. The item re-enters the claimable pool but is held off by the penalty period before it will be claimed again. See [work-store.md §Placement failure backoff](work-store.md#placement-failure-backoff).
