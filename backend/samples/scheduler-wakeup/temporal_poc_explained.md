# Temporal scheduler wake-up PoC explained

The Temporal PoC uses Temporal as a durable wake-work coordinator. It starts a
small, dedicated Temporal workflow for each scheduler wake event; that
workflow tells a Scheduler worker to perform bounded scheduling passes against
the Execution Store.

It does not move executions, task payloads, or node logic into Temporal. The
Execution Store still owns execution state, leases, fencing, capacity, and
claims.

## How the PoC works

1. The Task Executor creates durable execution state.

   As with the other PoCs, it writes a queued execution and a durable
   wake-outbox record.

2. The Task Executor starts a Temporal wake workflow.

   `TemporalWakePublisher` starts a workflow with an ID derived from the wake
   event:

   ```text
   scheduler-wake/<event-id>
   ```

   The workflow input is only the minimal hint:

   ```json
   {
     "version": 1,
     "event_id": "<wake-outbox-id>",
     "queue": "default"
   }
   ```

   Deriving the workflow ID from the event ID makes repeat publication
   idempotent: retrying the same outbox event targets the same workflow rather
   than creating unrelated wake workflows.

3. Temporal durably records workflow start.

   When Temporal accepts workflow start, the wake is stored in Temporal's
   persistence layer and remains present through Task Executor and Scheduler
   worker restarts.

4. A Scheduler Temporal worker receives the workflow task.

   The Scheduler-owned worker executes `SchedulerWakeWorkflow`. The workflow
   validates the hint and invokes the `scheduler_wakeup_poc_run_pass` activity,
   a narrow adapter around `SchedulingCore.run_pass(queue)`.

5. The scheduling activity claims real work from the Execution Store.

   The store transaction locks eligible rows with `FOR UPDATE SKIP LOCKED`,
   creates attempts, assigns fences and leases, marks executions claimed, and
   enforces capacity when configured. This remains the actual ownership
   decision; Temporal running the activity does not make it the authority for
   task ownership.

6. The workflow drains bounded batches.

   A pass returns `PassResult`, including `immediate_more`. If it is false,
   the workflow finishes. Otherwise it executes another scheduling-pass
   activity. After 128 passes it uses Continue-As-New, preventing unbounded
   workflow history while retaining the logical drain operation.

7. Failure is handled by Temporal retry plus store fencing.

   If the worker dies before an activity completes, Temporal retries or
   redelivers the workflow/activity task according to policy. A repeated
   activity can safely scan the same queue because the Execution Store locking
   and fencing prevent duplicate task claims.

   If a Scheduler later dies after claiming a task, the execution lease still
   expires in the Execution Store and normal recovery requeues it. Temporal
   retries do not remove the need for execution leases.

## Position in the execution-plane design

```text
Task Executor
    │
    │  1. transaction: execution + wake outbox
    ▼
Execution Store
    │
    │  2. start durable Temporal wake workflow
    ▼
Temporal persistence
    │
    │  3. workflow task delivered to Scheduler worker
    ▼
Scheduler wake workflow
    │
    │  4. scheduling-pass activity
    ▼
Execution Store durable claim
    │
    ▼
Task Executor dispatch
```

This replaces `pg_notify` as the Scheduler wake mechanism. Temporal does not
replace the workflow-execution engine in this PoC; it is evaluated only as a
durable transport/orchestration layer for Scheduler wake-up.

## Advantages

- The wake remains durable after Temporal accepts workflow start.
- Scheduler worker restarts do not lose wakes.
- Temporal supplies task delivery, retry, visibility, history, and operational
  tooling.
- Wake retries and bounded draining are explicit, inspectable workflow
  behaviour.
- Syntara already uses Temporal, reducing adoption friction compared with a
  completely new platform dependency.

## Limitation and applicability

Temporal is materially heavier than the other options. A wake has this path:

```text
start workflow
→ workflow task
→ activity task
→ database scheduling pass
→ workflow completion
```

That adds persistence and worker round trips for what is conceptually a queue
doorbell. In the local PoC it was slowest: about 350 tasks/s for the 100-task
batch, compared with about 488 for JetStream and 501 for in-process HTTP.
These are local PoC figures, but the extra orchestration work is real.

Temporal is strongest when durable, observable, retryable wake processing is
more important than minimum latency and using the existing Temporal platform
is acceptable for the execution plane. It is less compelling when scheduler
wake-up must remain fully independent of Temporal, or when HTTP plus recovery
or JetStream provides sufficient reliability with less overhead.
