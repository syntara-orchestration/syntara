# Scheduler wake-up PoC results

## Result summary

Each result is the median of five runs. A run creates 100 immediately eligible
tasks in the same logical queue, publishes one advisory `WakeHint`, and ends
only after all 100 claims have reached the fake dispatcher and its completion
has been persisted.

| Adapter | Median elapsed time for 100 tasks | Median throughput |
| --- | ---: | ---: |
| Local reference | 205.7 ms | 486.2 tasks/s |
| HTTP (FastAPI ASGI) | 199.7 ms | 500.7 tasks/s |
| JetStream (live local NATS) | 205.0 ms | 487.7 tasks/s |
| Temporal (local Temporal test server) | 285.5 ms | 350.3 tasks/s |

The HTTP number is an in-process ASGI measurement, not a TCP, load-balancer,
or cross-pod measurement. JetStream uses a live local NATS JetStream broker.
Temporal uses the SDK's local time-skipping test server, so it includes a real
workflow start, workflow task, activity, and workflow completion, but not the
latency of a production Temporal cluster. All variants use SQLite and the
sample fake dispatcher; they are comparative PoC numbers, not a production
capacity estimate.

## Shared order of operations

The transport never owns an execution and it receives no task payload. The
common data-plane sequence is:

1. The Task Executor calls `AsyncExecutionStore.enqueue(SubmitTask)`.
2. One transaction writes `POCExecution` in state `queued`, and writes a
   `POCWakeOutbox` row with the queue and wake-event ID.
3. The benchmark publishes one `WakeHint(version=1, event_id, queue)` after
   its 100 inserts. A normal producer can publish each committed outbox row;
   duplicate/coalesced hints are safe.
4. The adapter delivers only that hint to a Scheduler.
5. `SchedulingCore.run_pass(queue)` selects eligible rows using
   `FOR UPDATE SKIP LOCKED`, writes a `POCAttempt`, assigns a fencing token and
   lease, and changes each execution to `claimed`.
6. The fake dispatcher completes each valid claim. Completion verifies owner,
   attempt ID, fence, and unexpired lease before moving the execution to
   `succeeded`.

If publication fails, `WakeOutboxPublisher` leaves the outbox row pending with
a future retry time. If a Scheduler dies after claiming work, lease expiry and
`recover_expired` requeue it with a new wake intent. Those correctness paths
are covered by the sample tests but are not included in the timing runs.

## Adapter-specific wake path

### HTTP

`HTTPWakePublisher` posts the envelope to
`POST /internal/v1/scheduler/wake`. `SchedulerWakeReceiver` validates the
configured queue, sets a process-local `asyncio.Event`, and replies `202` with
`volatile` acceptance. Its per-queue drain loop clears the event before a
scheduling pass and repeats bounded passes while `immediate_more` is true.

For the recorded number, `httpx.ASGITransport` invoked the FastAPI endpoint in
the same process. A receiver restart after a `202` can lose the in-memory flag;
the durable execution/outbox data remains, and a configured recovery sweep is
needed to rediscover it.

### JetStream

`JetStreamWakePublisher` publishes the JSON envelope to the run-scoped subject
`execution.scheduler.wake.poc.<run-id>.<queue>`, with `Nats-Msg-Id` set to the
wake-event ID. JetStream durably accepts the message before the publisher
returns. `JetStreamWakeReceiver` uses one shared durable pull consumer. It
executes scheduling passes until the queue no longer reports immediate work,
then acknowledges the message; failures leave it unacknowledged for
redelivery.

The recorded run started an ephemeral `nats:2.10-alpine` container with
JetStream enabled, created a unique stream and consumer for each sample run,
then removed the container after measuring.

### Temporal

`TemporalWakePublisher` starts `scheduler_wakeup_poc` with a workflow ID of
`scheduler-wake/<event-id>`. The workflow validates its JSON-decoded envelope,
then invokes the named `scheduler_wakeup_poc_run_pass` activity. It loops while
the activity returns `immediate_more`, and uses Continue-As-New after 128
passes. The benchmark waits for that workflow to finish before recording the
run time.

The number includes workflow start and completion. It does not include a
production Temporal frontend, persistence backend, TLS, or worker network hop.

## Interpretation

The three values are close enough that they should not determine the production
choice. The main qualitative distinction remains durability and operational
ownership: HTTP is volatile and needs recovery sweeps; JetStream makes the wake
durable in the broker; Temporal makes it durable as workflow state but adds a
workflow/activity round trip. A PostgreSQL-backed multi-replica benchmark is
required before drawing throughput or latency SLO conclusions.
