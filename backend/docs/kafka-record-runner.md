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
The runner also probes handoffs from revoked partitions during normal operation.
Confirmed persistence releases their queue reservation even without reassignment.
Matching redeliveries denied new Execution capacity still check for accepted
Temporal work and can persist it without starting another workflow.
During graceful republish, the old runner retries parked handoffs without
filtering again or starting another workflow. It reserves their original
arguments before sending the start and retains them across drain cancellation
and partition revocation. The signed event worker client makes one RPC attempt
per start so it can distinguish direct rejections from uncertain outcomes. A
definite rejection releases the reservation and leaves the offset for replay.
For accepted or uncertain attempts, failed
recovery keeps the subscription draining and retries on later reconciliation.
This in-memory protection does not survive a process crash.
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
The publication lock follows the outstanding writes from its own batch. A
definitive broker rejection settles that write and leaves its offsets uncommitted.
A late definitive reply can settle the write while consumer shutdown continues.
The SDK retry loop has its own five-second limit. On an uncertain broker reply,
timeout or interruption, the adapter closes to new commits and position
operations immediately. Shutdown
confirms removal of any group member with a potentially outstanding commit.
An ambiguous skip batch also holds its publication lock until that fence is
confirmed.

Placement loss closes fetching and starts a bounded drain. Already admitted
handoffs may finish persisting accepted runs. Their resolved offsets may commit
only while still Kafka-assigned, under the same epoch and before the drain
deadline. Assignment loss always forbids that commit.

## Queues and content holds

Queue count, byte, per-partition and processing bounds limit local work. The
queue budget covers buffered source bytes and the encoded arguments of retained
handoffs, including handoffs for revoked partitions. Saving prepared arguments
releases the raw queue entry and transfers its reservation to the handoff. A
detached handoff still uses a record slot on its partition. A definitive rejection
rewinds to the original offset. An already reserved handoff can retry at capacity.
Queue overflow rewinds the unqueued tail and discards fetch
results from the old cursor while the rewind is pending. Numeric offset gaps are
valid for offsets the runner has never received. A checkpoint cannot cross a
previously delivered offset that still requires inspection.
If admission closes during a fetch, its unqueued records are also rewound.
Each partition task drains queued heads in order, with one handoff at a time,
releasing the shared processing slot between records.
After a restart, accepted runs recover from Execution or Temporal evidence on
redelivery. In-memory handoffs can retry while the runner owns them.

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

Local holds do not create per-message database rows.
A restart reads the uncommitted record again. Reassignment and a local runner
replacement on the same publication carry forward outstanding inspection and
delivery evidence. The runner saves a match and its receipt time before checking
execution storage or preparing a start. Replay on the same publication uses the
saved match and receipt time. A definitively rejected start can be retried when
the original Kafka payload is available. The runner checks for an existing
Execution or an accepted Temporal run by record identity, even when the Kafka
payload is unavailable. An oversized payload is classified during fetch. The
partition task checks for terminal delivery under the normal recovery deadline.
The runner tracks exact unresolved offsets and reserves room for another full
fetch before admitting new records for a partition. When space runs low, normal
intake pauses on that partition. The runner rotates single-record replay reads
across paused partitions and reserves space for each result before fetching.
An empty replay poll keeps its seek position and any late Kafka reply. If
repeated verified rewinds fill the in-memory budget, the runner moves existing
offsets to local temporary storage to make space for replay. Verification-only
checks for unresolved offsets use a separate worker slot so ready records can keep processing.
It can confirm a compacted record by its Execution identity and preserves
verified read gaps across local reassignment. A delivered
no-match can resolve locally. Position
recovery checks evidence below the proposed next offset and leaves later
evidence for replay. Resuming uses the verified Kafka cursor and discards
rewind requests from the previous cursor. Validation-only inspection during
position recovery never starts a workflow or creates a commit candidate.
A new publication revalidates held content using its new schema. A hold retained
after partition revocation does not block healthy sibling partitions.

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
