# Kafka record processing and recovery

The runner commits only offsets resolved in Kafka delivery order. A matching
record is resolved after Temporal acceptance is verified and the normal
PostgreSQL Execution is committed. Workflow completion is not required.

## Scheduling and redelivery

For each received record:

1. Derive the stable Execution UUID and Temporal workflow ID from the deployment,
   integration, source generation, workflow, subscription and Kafka coordinates.
2. Recover a confirmed normal Execution or retained signed Temporal acceptance
   before applying current filters, decoding rules, or admission checks.
3. If no accepted run exists, check current lifecycle, credentials, and capacity,
   then evaluate the filter and validate content. No-matches, filter errors, and
   known invalid content can complete locally under the offset-safety checks.
4. For a valid match, prepare detached start arguments in memory and start Temporal
   outside a database transaction. On duplicate or uncertain acceptance, verify
   retained signed arguments and recover the original run.
5. After verified acceptance, persist the normal Execution and scheduling
   confirmation in a short transaction, then advance the resolved prefix.

A failed or ambiguous start creates no pre-start Execution. A failed database
write retries the same accepted arguments in a fresh transaction, without
cancelling or starting another workflow. Existing Execution status is preserved.

There is no delivery ledger, delivery capacity table, terminal proof cache,
cleanup worker or independent handoff-recovery scanner. Interrupted handoffs
remain uncommitted in Kafka. Repair waits until that same source is consumed
again. Duplicate protection lasts while the normal Execution or Temporal
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

The runner reads current subscription eligibility on every processing advance.
It does not reuse an eligibility result for a timed interval.

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
`EventWorkerDefaults.HINT_TIMEOUT_SECONDS`. Half the budget permits audit
draining; the remaining time permits stopping the poller and cancelling pending
writes. Incomplete cleanup is logged without preventing database disposal.

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
assignment must remain verified.

See [initialization](eventstreams/kafka-initialization.md),
[connection testing](event-subscription-controls.md) and
[worker operations](kafka-worker-operations.md).
