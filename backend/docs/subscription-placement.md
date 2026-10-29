# Subscription placement and local supervision

This branch adds the placement provider and the local ownership contract. It uses
the worker registry and subscription placement fields supplied by #931 and the
Kafka runner admission/drain port supplied by #972. Process composition, fleet
fair-share reconciliation, Redis wiring and scheduling of independent background
loops belong to #988.

## Values and authority

`WorkerIdentity` contains the persisted `Installation.id` and a fresh process
UUID. `SubscriptionPlacementService.create(session_factory)` reads that namespace
and generates only the process UUID. Construct one provider per process and share
it with every local supervisor; never reuse a previous process UUID.

`WorkerMembership` records the confirmed membership deadline and draining flag.
`SubscriptionPlacementLease` records the subscription, owner, database observation
time and database expiry. These immutable SQLModel values are separate from
`SubscriptionSnapshot` and token-fenced `DeliveryClaim` values.

A lease value alone does not open admission. Pass
`placement=provider.authority(subscription_id)` to `SubscriptionSupervisor`.
The provider publishes authority only after a successful transaction commit and
session close. A monotonic deadline starts before database I/O and uses the
database's remaining lease duration, so request/commit latency reduces the local
budget. Local wall-clock time does not decide ownership.

The shared guard reserves a subscription before slow factory/startup calls and
releases that local reservation only after construction has settled and the old
runner has confirmed stop. Losing authority cannot reopen that old runner. A
different local supervisor cannot create a concurrent consumer through the same
guard. Shutdown errors retain the reservation for later cleanup.

## Provider hooks for #988

| Hook | Contract |
| --- | --- |
| `heartbeat_worker(worker, draining=...)` | Register/renew process membership with database time. Draining is permanent for this process incarnation; a late heartbeat cannot undo it. Draining prevents new claims and excludes the worker from live placement targets. |
| `list_live_workers()` | Return live, non-draining workers in this persisted deployment. |
| `claim_subscriptions(worker, limit=...)` | Claim at most 100 active unassigned/expired subscriptions; the manager supplies its deficit as the limit. Return usable leases only after commit. |
| `renew_placement(lease)` | Renew an owner-matching, still-unexpired lease using the latest lease value. A stale argument returns the current confirmed lease while it remains trusted, without extending it or reporting ownership loss. A foreign worker argument raises a validation error. Draining workers may renew leases during bounded shutdown. An expired renewal cannot resurrect ownership. |
| `reconcile_placement(subscription_id)` | Read ownership and expiry in a fresh transaction after an uncertain outcome. Confirmed stop is still required before a lost local guard can reopen. |
| `pending_reconciliation` | Candidate IDs whose outcomes must be reconciled, including uncertain batch commits and commits that outlasted their conservative local authority budget. |
| `distrust()` | Immediately revoke local trust when the process manager detects a database outage or another loss of authority. |
| `release_placement(lease)` | Release only after confirmed local stop, using the latest lease value. Compare owner, deployment and expiry so stale releases cannot clear another lease. |
| `prune_stale_workers(limit=...)` | Remove stale membership only after all dependent placement leases expire or are released. |

Claiming locks membership, then workflow, subscription and source. Publication and
source lifecycle operations retain their common workflow-before-subscription
order. Claim candidates and lifecycle rows use `FOR UPDATE SKIP LOCKED` so a
contended batch may return fewer candidates than requested. Renewal locks the
subscription before evaluating its unexpired conditional update. Pruning locks
membership to serialize against heartbeat and claim/renewal, and checks dependent
leases before deletion.

Lease mutations update only owner and expiry fields. They do not change source
identity, `configuration_revision`, user timestamps or actor attribution. No
transaction or row lock spans Kafka or Temporal I/O. All local mutations serialize
inside the provider; large fleets will need to measure database latency and batch
cost before tuning this boundary.

`PlacementUncertainError` means the database outcome is unknown. Do not start a consumer
or blindly reclaim that subscription. Reconcile the exposed pending IDs in fresh
sessions; a rollback, transfer or expiry returns `PlacementLost`. Cancellation
during commit also revokes trust. Never infer success or failure solely from a
timeout.

## Supervisor and runner hooks

`apply(snapshot)` applies a desired target under current placement authority.
`retry()` preserves existing local restart/backoff semantics while ownership is
valid. A connection failure retains its owned placement instead of releasing and
reclaiming it on every retry.

If another local supervisor still holds the reservation, an active target reports
`blocked` with reason `local_runner_busy`, without consuming connection retry
budgets. Reapply after that supervisor confirms stop; the contender then starts
under the same current placement lease. An inactive target clears that local
contention observation.

The runner factory returns an unstarted runner. The supervisor binds its live
placement guard and keeps admission closed throughout `start()`. It checks
authority after factory completion, after startup, and synchronously before
`open_admission()`. The runner consults that guard before new processing and fetch
admission. A local expiry watchdog runs independently of factory/startup and of
the manager's heartbeat/renewal loops.

Each processing invocation also receives its runner's live admission guard.
Lookups and resource validation can be slow, so the provider rechecks the guard
after those waits, before inspection acquisition, and before new execution
preparation. It does not store a global callback on a shared processing service.
Frozen preparations and already admitted scheduling retain their independent
delivery-token authority.

`placement_lost()` is the manager's explicit loss hook. The guard closes new
admission immediately, then the supervisor uses `close_admission()` to pause and
bound drain, followed by `stop()`. Failed stops remain visible as draining and
prevent reacquisition/release. `drain()` and `stop()` remain the shutdown hooks.
Keep membership/owned-lease renewal running during drain; release placement only
after `stop()` confirms completion.

Shutdown observes an owned cleanup task with a bounded wait. A late or
cancellation-resistant drain cannot hold the manager's callback indefinitely or
prevent a client-stop attempt. The supervisor retains the task, runner and local
reservation until drain, stop and the serving task have all settled. Repeated
stop requests reuse that cleanup. After an incomplete shutdown, #988 must call
stop/reapply again to collect its final result before releasing or reacquiring.

Placement loss does not revoke Kafka assignment or a delivery token. Already
admitted work may finish using valid delivery claims. Resolved offset commits
still require current Kafka assignment, local epoch and the drain deadline.
Placement expiry never clears delivery evidence, establishes an RPC result, or
cancels an accepted Temporal execution. Prepared recovery remains independently
callable without a subscription placement lease or Kafka consumer.

## Candidate settings and verification

These provider defaults are **unvalidated** and centrally defined in
`EventPlacementDefaults`. Settings reject nonpositive values and require both
expiry durations to exceed the heartbeat interval.

| Environment setting | Candidate default |
| --- | --- |
| `APP_EVENT_WORKER_HEARTBEAT_INTERVAL_SECONDS` | 20 seconds |
| `APP_EVENT_WORKER_LIVENESS_SECONDS` | 60 seconds |
| `APP_EVENT_SUBSCRIPTION_LEASE_SECONDS` | 60 seconds |

These are separate from delivery leases and Kafka group/session timeouts. The
deployment must leave enough margin for database latency, retry, process pauses
and clock behavior. Placement permits temporary takeover overlap; it is not
strict execution fencing.

The isolated tests describe commit acknowledgement, uncertain reconciliation,
owner/deployment checks, lifecycle lock order, expired renewal rejection,
stop-before-reacquisition/release, startup races, backoff and independent recovery.
They do not establish live PostgreSQL contention guarantees or validated fleet
capacity. Concurrent database and broker failure testing remains necessary before
release.
