# HTTP scheduler wake-up PoC explained

The HTTP PoC treats HTTP as a fast, advisory doorbell from the Task Executor
to the Scheduler. The Scheduler still decides what runs by querying and
claiming work from the Execution Store; the HTTP request never carries an
execution payload or assigns work to a particular Scheduler replica.

## How the PoC works

1. The Task Executor persists work in the Execution Store.

   `AsyncExecutionStore.enqueue()` atomically creates a queued execution
   record and a scheduler-wake outbox record. The execution is the durable
   source of truth. The outbox records that scheduling should occur, even if
   notification initially fails.

2. The Task Executor publishes a minimal wake hint.

   `HTTPWakePublisher` sends the following envelope to
   `POST /internal/v1/scheduler/wake`:

   ```json
   {
     "version": 1,
     "event_id": "<wake-outbox-id>",
     "queue": "default"
   }
   ```

   It does not send credentials, node configuration, the task body, or an
   execution ID to run.

3. A Scheduler replica accepts the hint.

   `SchedulerWakeReceiver` validates that it is configured for the hinted
   queue, sets a process-local `asyncio.Event` for that queue, and replies
   with HTTP `202`.

   The response means only that this Scheduler process has remembered it
   should inspect the queue. It does not mean work has been claimed or
   executed.

4. The local Scheduler drain loop claims real work from the Execution Store.

   The drain loop clears the event before querying, then calls
   `SchedulingCore.run_pass(queue)`. The store selects eligible queued
   executions in a transaction using `FOR UPDATE SKIP LOCKED`, and persists a
   claimed state, attempt record, lease expiry, fencing token, and optional
   capacity reservation.

   More than one Scheduler may receive the same wake hint, but only one can
   claim each execution. Duplicate and coalesced wake hints are therefore
   harmless.

5. The Scheduler dispatches claimed work.

   The PoC uses a fake dispatcher which records completion. In the execution
   plane, this is the point at which the Scheduler selects capacity and asks a
   Task Executor to execute the claimed work node.

6. Durable state supports recovery.

   If publication fails, `WakeOutboxPublisher` leaves the outbox row pending
   with a future retry time. If a Scheduler dies after a claim, its lease
   expires and `recover_expired` requeues the work with a fresh wake intent.

## Position in the execution-plane design

This approach fits between the Task Executor/Execution Store write path and
the Scheduler's durable queue-claim path:

```text
Task Executor
    │
    │  1. persist execution + wake-outbox transaction
    ▼
Execution Store
    │
    │  2. HTTP wake hint: “queue may have work”
    ▼
Scheduler HTTP receiver
    │
    │  3. local queue drain
    ▼
Scheduler
    │
    │  4. durable claim / lease / fence from Execution Store
    ▼
Task Executor dispatch
```

It replaces `pg_notify` only as the low-latency Scheduler wake mechanism. It
does not replace the Execution Store, durable claim protocol, leasing,
fencing, capacity accounting, or the API used to dispatch work.

It preserves the execution-plane separation:

- The Control Plane creates workflow intent.
- The Task Executor performs execution-plane submission and ultimately runs
  the node.
- The Execution Store owns durable execution state.
- The Scheduler decides which durable work it may claim and dispatch.
- HTTP is only the hint transport between Task Executor and Scheduler.

## Advantages

- Simple to operate when Task Executors can reach the Scheduler service.
- Low overhead and low latency.
- Does not depend on PostgreSQL notifications, PgBouncer behaviour, or a new
  message broker.
- The small envelope stays decoupled from task-schema changes.
- Multi-replica safety comes from the database claim transaction, not from
  HTTP routing.

## Limitation and applicability

HTTP `202` acceptance is volatile. A Scheduler can accept a hint, then restart
before it claims work; its process-local event is then lost. The execution
remains queued in the Execution Store, but a recovery sweep or equivalent
durable reconciliation must rediscover it.

HTTP is a strong MVP candidate when a bounded recovery delay after Scheduler
failure is acceptable, Scheduler reachability is reliable, and low operational
complexity matters most. It is a weaker fit if successful notification must
survive Scheduler process loss without a recovery sweep; JetStream and Temporal
offer durable alternatives for that particular requirement.
