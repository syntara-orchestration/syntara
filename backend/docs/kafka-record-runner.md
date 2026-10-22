# Kafka record runner recovery

The single-subscription runner uses explicit resolution-only Kafka commits.
Validation-only inspection never grants workflow admission or commit permission.
It may read back an already delivered, uninspected offset window while a recovery
fence closes normal admission. Kafka ownership and the assignment epoch are still
required for every seek, fetch and commit. This is not a general replay interface.

## Duplicate lookup and shared gates

Inject the completed `TerminalDeliveryCache` lookup and the same
`RecordProcessingGate` instance into the runner and any injected processing
service. The process composition owns the shared provider, lifecycle/dependency
reconciliation and placement lease trust. This runner owns their enforcement;
it does not create a Redis pool, lease store or process manager. Without an
injected shared gate, the runner retains database reconciliation and does not
use the cached duplicate path.

Before the first record, reconcile pending delivery evidence, complete verified
partition initialization and verify lifecycle/resource eligibility. Reconcile
again at most every existing transient-probe interval (currently 60 seconds),
and invalidate that local state after blocked work, a cursor reload, an ownership
change or an administrative recovery fence. Only bounded per-assigned-partition
state is retained; there is no local map of terminal outcomes.

Within that interval, an admitted head uses the cache-aside lookup before
decoding or schema evaluation. A validated scheduling proof preserves its
original terminal outcome with no per-record PostgreSQL session, Temporal call,
claim or preparation. A miss/error must inspect PostgreSQL; absence is never
inferred from Redis. Frozen unresolved deliveries recover their saved context.
Cancellation outcomes stay on the database path. Rejected outcomes remain held
while the required author-accessible activity log is unavailable.

Gate reads must be local, bounded and fail closed for unknown or stale evidence.
`admission_open(snapshot)` requires current lifecycle/resources and a trusted,
unexpired placement lease. `resolution_open(snapshot)` must reject known database
outages, failed required durable writes, source-incarnation uncertainty and
administrative recovery blocks. Required durable failures observed by processing
or initialization call `dependency_failed(snapshot)`. A locally created
administrative fence and discovered lifecycle/source evidence failures also
invalidate that shared trust. Only authoritative process reconciliation may
reopen the shared gate after the hold is resolved. Source correction/restore still
requires the completed cache provider's external epoch coordination.

The runner also checks local content/unknown-content gates, initialized partition
state, assignment and epoch before using a cached proof for a new head. A later
permanent-content, pending-inspection or unknown-content hold does not invalidate
an earlier durably resolved prefix. Expiry of the local admission reconciliation
also leaves that prefix intact. Its commit still requires current ownership,
initialized partition state, an open shared resolution gate, no administrative
fence, and time remaining in any drain deadline. These rules apply with and
without an injected gate. The held record itself remains non-committable.

Commit candidates come only from received heads
resolved in delivery order; numeric Kafka offset gaps are valid. A proof grants
neither partition ownership nor an initial/group checkpoint. Cache population
after durable scheduling is owned by the completed admission service; optional
cache write failures do not undo scheduling or eligible commits.

## Placement loss and partition readiness

`RecordRunnerControl.close_admission()` starts a full runner drain by setting
`_closing=True`, pausing fetching and applying the existing shutdown deadline.
Reopening intake requires a new runner instance. A closed/expired placement gate
also triggers this path from the run loop. No new head is admitted, but an already admitted
handoff may finish with its valid delivery claim. Resolution can commit during
drain only while still Kafka-assigned, under the same local epoch, before the
deadline, and with the resolution/dependency gate open. Unfinished frozen
handoffs remain available to independent database/Temporal recovery, which does
not require placement or Kafka ownership.

The completed initialization service preserves its immutable initial partition
set: first-activation members start at the read-committed visible end; added
partitions start at retained beginning. Saved boundaries and verified group
commits retain their existing precedence. Adding a partition initializes only
that partition, without resetting ready partitions or creating an administrative
recovery fence. `ready_partitions` reports the initialized subset of the current
assignment, including during partial startup; client startup alone is not proof
that all partitions are ready. Ordinary partition-local broker initialization
failures hold that partition independently; explicit source/database evidence
failures close the shared resolution gate.

## Content inspection evidence

Before decoding, the processing service commits an ordinary delivery row with
`last_error_code=content_inspection_pending` and a finite, token-fenced inspection
claim. This records unknown content status without storing the source body.
The marker remains protective after lease expiry, cancellation and restart.

Successful validation-only inspection replaces the marker with
`content_validated`. Normal processing keeps the marker until durable Execution
preparation is frozen. A permanent decoding/schema error replaces it with its
safe error code and remains unresolved until the required activity log exists.
Failed inspection finalization retains the pending marker. Dependency, permission,
quota and capacity failures do not become permanent content decisions.

Gap reconciliation, boundary confirmation and retention verification all respect
pending inspection evidence. Missing source records or unavailable evidence must
leave the gate closed. Shutdown and revocation use their existing drain deadline;
they cannot turn unresolved inspection into acknowledgement permission.

The implementation reuses the existing delivery schema and requires no DDL
migration. Unit tests use isolated storage and transport adapters; they do not
establish live database durability, broker connectivity or cross-process behavior.

## Safe code rollback

Do not roll recovery/cleanup code back to a version that ignores
`content_inspection_pending` while such rows remain. Stop new intake and use the
current inspection and recovery services to reconcile every pending inspection
first. Preserve permanent error rows and frozen/ambiguous Execution evidence.

If a pending inspection cannot be completed, retain the marker and keep the
compatible recovery/cleanup code deployed. Lease expiry, row deletion, clearing
the marker, or advancing Kafka offsets are not safe substitutes for evidence.

Queue, concurrency and drain defaults are configured through the documented
`APP_EVENT_*` settings in `.env.example`. Changes apply on runner restart.

See [event subscription controls](event-subscription-controls.md) for revision-checked
operator actions, durable shutdown acknowledgements, retirement guards and the
additional control-coordination migration.
