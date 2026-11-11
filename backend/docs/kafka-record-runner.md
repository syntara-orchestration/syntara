# Kafka record processing and recovery

The runner commits only offsets resolved in Kafka delivery order. A matching
record is resolved after Temporal acceptance is verified and the normal
PostgreSQL Execution is committed. Workflow completion is not required.

## Scheduling and redelivery

For each received record:

1. Derive the stable Execution UUID and Temporal workflow ID from the deployment,
   integration, source generation, workflow, subscription and Kafka coordinates.
2. Reuse a matching confirmed normal Execution when one exists.
3. Otherwise look up the stable Temporal workflow ID and verify its signed
   start arguments. Recover an accepted run using its original version, input,
   principal and timestamps.
4. Only confirmed absence permits current lifecycle, credential, payload and
   capacity checks, followed by preparation in memory.
5. Start Temporal outside a database transaction. After acceptance, persist the
   normal Execution and scheduling confirmation in a short transaction.
6. Advance the resolved prefix only after that transaction commits.

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

Invalid content stays uncommitted while the required author-visible activity
logging is unavailable. Local holds do not create per-message database rows.
A restart reads the uncommitted record again. Validation-only inspection during
position recovery never starts a workflow or creates a commit candidate.
A new publication revalidates held content using its new schema. A hold retained
after partition revocation does not block healthy sibling partitions.

## Initial positions and automatic recovery

The saved first topic partition set starts at the read-committed visible end.
Partitions added later start at retained beginning. Saved boundaries survive
retries; ready partitions may continue while an added partition initializes.

Valid group commits govern normal resumption. Missing or out-of-range offsets
recover automatically from retained beginning. A partition token and revision
keep the selected boundary stable across interruptions. Local tasks must drain,
and source identity and assignment must remain verified.

See [initialization](eventstreams/kafka-initialization.md),
[connection testing](event-subscription-controls.md) and
[worker operations](kafka-worker-operations.md).
