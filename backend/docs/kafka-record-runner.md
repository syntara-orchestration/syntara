# Kafka record processing and recovery

The runner commits only offsets resolved in Kafka delivery order. A matching
record is resolved after Temporal acceptance is verified and the normal
PostgreSQL Execution is committed. Workflow completion is not required.

## Scheduling and redelivery

For each received record:

1. Derive the stable Execution UUID and Temporal workflow ID from the deployment,
   integration, source generation, workflow, subscription and Kafka coordinates.
2. Evaluate the publication's CEL filter locally. No-match and evaluation-error
   outcomes need no Execution lookup or Temporal call. Before committing a batch
   containing local skips, lock and validate its authoritative subscription
   revision until the Kafka commit settles. A republished revision leaves the
   old batch uncommitted for replay.
3. For matches, reuse a matching confirmed normal Execution when one exists.
4. Otherwise check current lifecycle, credentials and capacity, then prepare
   the matching record in memory.
5. Start Temporal outside a database transaction. After verified acceptance,
   persist the normal Execution and scheduling confirmation in a short
   transaction, then advance the resolved prefix.

Decode or schema failures check confirmed Execution or verified Temporal
acceptance before auditing invalid content and completing a local skip under
the offset-safety checks. This lets redelivery repair an earlier accepted run
with its original input even after a schema change.

A failed or ambiguous start creates no pre-start Execution. Handoff recovery
looks up the stable Temporal workflow ID and verifies its signed start arguments.
A failed database write retries the same accepted arguments in a fresh
transaction, using the original version, input, principal and timestamps.
Existing Execution status is preserved.

There is no delivery ledger, delivery capacity table, terminal proof cache,
cleanup worker or independent handoff-recovery scanner. Interrupted handoffs
remain uncommitted in Kafka. The runner retries saved handoffs even without new
records; after a restart, repair waits until that same source is consumed again.
During graceful republish, the old runner retries parked handoffs without
filtering again or starting another workflow. It retains their original
arguments across partition revocation and cannot be replaced until Execution
persistence is confirmed. Failed recovery keeps the subscription draining and
retries on later reconciliation; this in-memory protection does not survive a
process crash.
Duplicate protection lasts while the normal Execution or Temporal
evidence remains available; deleting both can permit a new start on redelivery.

## Ownership and shared gates

Each subscription is leased to one worker. Kafka assignment and a local
assignment epoch separately guard every seek, fetch and commit. A resolved
Execution does not establish partition ownership or a group checkpoint.

Known database failures close the shared scheduling/commit gate until fresh
database reconciliation. An uncertain source fences only that source until
Kafka identity is verified again. Recovery tokens fence only their partition.
Redis carries reconciliation hints only; losing a hint does not change the
database source of truth.

The runner refreshes subscription eligibility between batches. Buffered records
use shared local gates; matches also check current admission before starting.
Local skip checkpoints validate the authoritative revision once per commit batch.
The five-second commit wait bounds only the caller's wait. The retained commit
task keeps the publication lock until the broker operation settles. An ambiguous
failure closes the consumer and requires broker-confirmed membership removal
before releasing the lock. If Kafka is unavailable, publication remains blocked
until that fence can be confirmed. Shutdown also retains the runner while such a
commit or fence is outstanding.

Placement loss closes fetching and starts a bounded drain. Already admitted
handoffs may finish persisting accepted runs. Their resolved offsets may commit
only while still Kafka-assigned, under the same epoch and before the drain
deadline. Assignment loss always forbids that commit.

## Queues and content holds

Queue count, byte, per-partition and processing bounds limit local work. Overflow
rewinds the unqueued tail rather than skipping records. Numeric offset gaps are
valid; later received records cannot advance past an unresolved earlier head.
If admission closes during a fetch, its unqueued records are also rewound.
Each partition task drains queued heads in order, with one handoff at a time,
releasing the shared processing slot between records.
Accepted runs recover from Execution or Temporal evidence on redelivery rather
than from a saved in-memory handoff. Inspection of oversized records uses a
bounded timeout and shares the processing concurrency limit.

Known invalid content emits a sanitized record-rejection event through the
existing platform OTEL audit pipeline. Activity logs are deferred. Audit failure
does not block an otherwise eligible skip and audit delivery is never offset
evidence. The skip remains tied to its source, configuration revision, assignment
epoch, current lifecycle/dependency gates, and all earlier records' completion.
Rejected-record audit writes use the existing `audit_writer_max_concurrent_writes`
setting to bound pending background tasks as well as active writes. At capacity,
the audit event is dropped with an operational warning; an otherwise safe skip
still proceeds. Other audit callers and transactional audit writes retain their
existing behavior.

After consumer draining, the standalone worker bounds audit cleanup by
`EventWorkerDefaults.HINT_TIMEOUT_SECONDS`. It waits only for inserts started in
that process, reserving half the budget for cancellation. It never starts the
shared outbox poller, claims or deletes shared rows, or exports audit events to
OTLP. The existing platform publisher delivers those rows. A blocked audit
collector therefore cannot leave an export thread running in the Kafka process.
Incomplete insert cleanup is logged without preventing database disposal.

Uninspected content and unknown dependency/source state remain held. Local holds
and skips create no delivery-ledger rows. A restart re-evaluates uncommitted work.
Validation-only inspection behind a recovery fence never starts a workflow or
creates a commit candidate. Accepted runs recover their original signed
arguments before current content rules can discard a redelivered record.

## Initial positions and automatic recovery

The saved first topic partition set defaults to the read-committed visible end.
Partitions added later default to retained beginning. Published reading settings
can override these choices for partitions without saved boundaries. Saved
boundaries survive retries and republish; ready partitions may continue while
an added partition initializes.

Valid group commits govern normal resumption. Missing or out-of-range offsets
use the published `fail`, `earliest`, or `latest` policy, defaulting to earliest.
A partition token and revision keep a selected policy and boundary stable across
interruptions and republish. Local tasks must drain, and source identity and
assignment must remain verified. Any saved handoff below the recovery boundary
must have confirmed Execution persistence before recovery can advance. Normal
commits and oversized-record handling also cannot cross an unresolved saved handoff.

See [initialization](eventstreams/kafka-initialization.md),
[connection testing](event-subscription-controls.md) and
[worker operations](kafka-worker-operations.md).
