# JetStream scheduler wake-up PoC explained

JetStream uses a durable message broker as the Scheduler's doorbell. Like the
HTTP PoC, it does not put task execution into JetStream: the Execution Store
remains authoritative for task state, eligibility, claims, leases, and
fencing. JetStream only durably records that a queue may have work.

## How the PoC works

1. The Task Executor persists the execution and wake intent.

   `AsyncExecutionStore.enqueue()` creates a queued execution and a
   `POCWakeOutbox` record in the same transaction.

2. The outbox publisher creates a durable JetStream message.

   `JetStreamWakePublisher` publishes only this wake envelope:

   ```json
   {
     "version": 1,
     "event_id": "<wake-outbox-id>",
     "queue": "default"
   }
   ```

   The message goes to a run-scoped subject:

   ```text
   execution.scheduler.wake.poc.<run-id>.default
   ```

   It sets `Nats-Msg-Id` to the event ID, enabling JetStream broker-side
   de-duplication within its configured deduplication window.

3. JetStream confirms durable acceptance.

   The publisher waits for JetStream's publish acknowledgement before
   returning `durable` acceptance. Once acknowledged, the wake message is
   stored by JetStream and survives a Scheduler process restart.

4. Scheduler replicas share one durable pull consumer.

   Each Scheduler runs a `JetStreamWakeReceiver` against the same durable
   consumer name. JetStream gives each wake message to one consumer replica at
   a time.

   This reduces duplicate wake processing, but it is not the correctness
   mechanism. The Scheduler still claims executions transactionally from the
   Execution Store, because duplicate delivery remains possible.

5. The Scheduler drains and then acknowledges.

   On receipt, the adapter validates the envelope and queue, calls the
   Scheduler's bounded scheduling pass, and repeats while the pass reports
   immediately eligible work. It acknowledges the JetStream message only after
   that drain succeeds. During a long drain it sends periodic `in_progress`
   acknowledgements to extend the acknowledgement deadline.

6. Failures lead to redelivery.

   If the Scheduler or receiver fails before acknowledgement, the message
   remains pending. JetStream redelivers it after `AckWait`. The resulting
   duplicate scheduling pass is safe because `FOR UPDATE SKIP LOCKED`,
   attempts, fencing tokens, and leases in the Execution Store decide which
   Scheduler owns each task.

## Position in the execution-plane design

```text
Task Executor
    │
    │  1. transaction: execution + wake outbox
    ▼
Execution Store
    │
    │  2. publish minimal wake hint
    ▼
JetStream stream
    │
    │  3. durable pull delivery to one Scheduler replica
    ▼
Scheduler
    │
    │  4. claim eligible tasks from Execution Store
    ▼
Task Executor dispatch
```

JetStream replaces `pg_notify` as the wake transport. It does not replace
PostgreSQL as the execution-state store or make JetStream the task queue.

## Advantages

- Wake hints survive Scheduler downtime after JetStream acknowledgement.
- Scheduler replicas can scale independently through a shared durable
  consumer.
- Redelivery occurs automatically after an unacknowledged failure.
- A Task Executor can publish while no Scheduler is connected.
- Broker metrics can show pending, redelivered, and acknowledged wake hints.
- Multi-replica task safety remains enforced by the database claim protocol.

## Operational choices in the PoC

The PoC uses one shared durable pull consumer, explicit acknowledgements,
file-backed JetStream storage, a five-second acknowledgement window, and a
bounded stream capacity.

A production design needs decisions on JetStream clustering and persistent
volumes, stream-retention and capacity limits, acknowledgement timeouts,
subject/tenant isolation, TLS and authentication, network policy, and the
consumer topology for queues and Scheduler pools.

## Limitation and applicability

JetStream makes notification durable, but introduces a new stateful platform
dependency. It also cannot make a database commit and a broker publish one
atomic operation:

```text
commit execution/outbox → publish to JetStream
```

If a process dies after the database commit but before publishing, the wake is
not in JetStream yet. The durable outbox and its retry/reconciliation process
therefore remain required.

JetStream is strongest when a wake should survive Scheduler downtime without
depending primarily on a periodic recovery sweep, and the team is comfortable
operating a small durable broker. It is a middle ground: more durable and
decoupled than HTTP, but lighter-weight and less workflow-oriented than
Temporal.

## Why JetStream rather than core NATS

Core NATS is live pub/sub. If no Scheduler subscriber is connected at the
instant the Task Executor publishes, the wake is lost:

```text
Task Executor publishes wake
    │
    ├─ Scheduler currently connected → receives it
    └─ Scheduler unavailable or restarting → wake is lost
```

JetStream adds durable persistence, acknowledgement, redelivery, shared
durable consumers, broker-side de-duplication through `Nats-Msg-Id`, and
visibility of pending/redelivered wake hints:

```text
Task Executor publishes wake
    │
    ▼
JetStream persists it
    │
    ▼
One Scheduler replica receives it
    │
    ├─ drains queue successfully → ACK, message is complete
    └─ dies or fails → no ACK, message is redelivered
```

Core NATS can still be used as a volatile low-latency hint, provided the
design accepts periodic Execution Store recovery sweeps for missed wake-ups.
In that mode it has similar delivery semantics to the HTTP PoC while adding a
broker dependency. For the durable-broker option, JetStream is the required
NATS capability.
