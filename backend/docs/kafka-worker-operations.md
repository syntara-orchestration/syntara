# Control-plane Kafka runtime configuration and local operation

The existing Kafka worker runs with
`python -m syntara.eventstreams.consumer_entrypoint`, independently of API,
workflow execution and background workers. The opt-in local compose profile runs
that entrypoint directly using the backend image. Operator-managed Kubernetes
deployment, CRD controls, container launchers and deployment health probes are
deferred to M2. This guide covers backend configuration, local compose and runtime
recovery safeguards. Kafka infrastructure, broker ACLs and broker credentials
remain customer managed; the local broker example is disposable development data.

## Configuration contract

`APP_EVENTSTREAM_ENABLED` defaults to `false`. Both local Kafka compose profiles
are opt-in; plain `podman-compose up` does not start a broker or Kafka worker.
The backend `services-run` helper explicitly selects the `eventstream` profile;
its consumer still exits without connecting when the feature flag is false.
An enabled worker with zero active subscriptions stays running and scans prepared
deliveries. Stopping every Kafka worker stops both consumption and prepared
recovery; recovery waits for a compatible worker to return.

Keep terminal retention identical across every process sharing the database.
For a retention change, unpublish affected workflows, drain and stop the whole pool, then
apply the [cache maintenance procedure](#cache-maintenance), including external
epoch rotation before shorter cleanup bounds, and restart with one consistent
value before resuming intake. Do not start a
second pool with a different retention value against the same database. Automatic
deployment rollout controls are part of the deferred M2 operator integration.

These settings are read at process/runner startup. The backend Settings defaults,
root and backend `.env.example`, and local compose worker agree:

| Environment variable | Default |
| --- | ---: |
| `APP_EVENTSTREAM_ENABLED` | `false` |
| `APP_EVENT_MAX_VALUE_BYTES` | `262144` |
| `APP_EVENT_MAX_ENVELOPE_BYTES` | `1048576` |
| `APP_EVENT_MAX_HEADERS` | `128` |
| `APP_EVENT_WORKER_HEARTBEAT_INTERVAL_SECONDS` | `20` |
| `APP_EVENT_WORKER_LIVENESS_SECONDS` | `60` |
| `APP_EVENT_SUBSCRIPTION_LEASE_SECONDS` | `60` |
| `APP_EVENT_FETCH_MAX_RECORDS` | `100` |
| `APP_EVENT_QUEUE_MAX_RECORDS` | `100` |
| `APP_EVENT_QUEUE_MAX_BYTES` | `8388608` |
| `APP_EVENT_PARTITION_MAX_RECORDS` | `10` |
| `APP_EVENT_PROCESSING_CONCURRENCY` | `8` |
| `APP_EVENT_FETCH_TIMEOUT_MS` | `100` |
| `APP_EVENT_DRAIN_TIMEOUT_SECONDS` | `20` |
| `APP_EVENT_DELIVERY_RETENTION_SECONDS` | `3600` |
| `APP_EVENT_TEMPORAL_HISTORY_RETENTION_SECONDS` | `86400` |
| `APP_EVENT_DELIVERY_CACHE_ENABLED` | `false` |
| `APP_EVENT_DELIVERY_CACHE_EPOCH` | unset; externally managed UUID |
| `APP_EVENT_DELIVERY_CACHE_TTL_SECONDS` | `60` |
| `APP_EVENT_DELIVERY_CACHE_TIMEOUT_SECONDS` | `1` |
| `APP_EVENT_DELIVERY_CACHE_SKEW_SECONDS` | `1` |
| `APP_EVENT_DELIVERY_CACHE_CLOCK_ERROR_BOUND_SECONDS` | unset; established cross-clock error bound |

Placement membership and subscription leases are separate from delivery claim
leases. Their expiry durations must exceed the heartbeat interval and leave
margin for database latency and process pauses. These are candidate defaults,
not validated fleet capacity or failover guarantees. See
[subscription placement](subscription-placement.md) for ownership and drain rules.

Terminal-proof caching remains disabled even when Redis is configured. Enabling
it requires an externally managed, nonzero epoch and an established clock-error
bound below the configured skew margin. Compose inherits those optional trust
inputs from the caller without supplying a default epoch or clock bound.
Retain the same epoch across ordinary process/pod restarts. Do not generate an
epoch per startup or keep its authority solely in PostgreSQL being restored.
Missing or invalid epoch/clock trust inputs disable terminal-cache reads and
writes, even when caching is requested. PostgreSQL processing remains available.
Invalid durations or a non-positive proof window still fail Settings validation.
The proof window is capped by terminal retention; see
[record runner cache safeguards](kafka-record-runner.md#duplicate-lookup-and-shared-gates).
TTL is measured from the original terminal resolution, not the latest read or
repopulation. The timeout bounds the total operation, including connection
acquisition and any retries, rather than granting a new deadline per attempt.

Local compose's `stop_grace_period` is 60 seconds. Keep termination grace longer
than the configured drain deadline **plus** membership/lease release and shared
client/database cleanup. The default drain is 20 seconds; the remaining grace is
cleanup headroom, not a validated worst-case shutdown guarantee.
When increasing the drain deadline, also increase `stop_grace_period`.

Queues and raw-byte bounds apply per subscription; processing concurrency is
shared across consumers and recovery in one worker. Candidate decoding limits
are `APP_EVENT_MAX_VALUE_BYTES=262144`, `APP_EVENT_MAX_ENVELOPE_BYTES=1048576` and
`APP_EVENT_MAX_HEADERS=128`. Broker fetch batches may exceed fetch byte limits;
these values are application bounds, not measured memory or throughput promises.

The following are fixed implementation bounds in `syntara.core.constants`, not
additional environment variables:

| Control | Current bound |
| --- | --- |
| Authoritative reconciliation | every 30 seconds, 10% jitter; best-effort Redis wakeups |
| Parallel subscription startup / attempt deadline | 8 / 30 seconds |
| Shared preparation / finalization operations | 8 / 8 |
| Immediate transient attempts / maximum backoff / later probes | 5 / 30 seconds / 60 seconds |
| Delivery claim lease / renewal interval | 60 seconds / 20 seconds; token-fenced renewal during active handoff |
| Prepared recovery scan interval / batch maximum | 60 seconds / 100 deliveries |
| Temporal RPC timeout / history safety margin | 10 seconds / 300 seconds |
| Capacity pause / resume thresholds | 3,000,000 / 2,500,000 retained delivery rows |

Active scheduling and recovery renew their committed delivery claim every
`CLAIM_RENEWAL_INTERVAL_SECONDS=20`, including waits for preparation/finalization
capacity and Temporal calls. Renewal uses fresh transactions and the same token;
lost ownership or a renewal failure stops the local operation. Completion and
cancellation stop and await the renewal task. Each renewal must finish within
one renewal interval, including connection acquisition and commit, or the local
operation is blocked. Recovery claims each delivery only
when ready to process it. Claim leases, Redis cache lifetimes and terminal
evidence retention are independent.
Unlike these fixed bounds, terminal-proof TTL and operation deadlines use the
cache settings above and require the external trust inputs when caching is enabled.

Terminal delivery retention is a **strictly positive minimum duration from
`resolved_at`**, not a storage cap or an automatic deletion deadline. Cleanup also
requires authoritative Kafka committed-position evidence and respects recovery
holds. Unresolved records, pending content inspection and frozen/ambiguous
Execution evidence never expire merely because the minimum duration passed.
Budget storage and monitor capacity separately. Redis is a disposable hint/cache;
PostgreSQL and Kafka positions remain authoritative.

If Kafka re-reads a record after its terminal delivery row was cleaned up, the
worker checks the retained Execution's original identity, frozen input fingerprint
and confirmed scheduling metadata. Matching confirmed evidence restores the
scheduled delivery without another Temporal start or a new retention timestamp.
Prepared-only or conflicting Execution evidence remains blocked.

### Automatic delivery cleanup

Each enabled Kafka worker runs an independent cleanup task, including workers
with no assigned subscriptions. No additional process, placement lease or Redis
coordination is required. Stopping the entire worker pool also stops cleanup.

Cleanup scans only its persisted deployment namespace. The cursor advances past
protected or unverifiable records and revisits them on later sweeps. A fixed
database-time cutoff bounds each sweep so sustained arrivals cannot indefinitely
extend an early source's page. Cursor state is process-local; restarting repeats
checks without granting permission to remove evidence.

Read-only Kafka clients inspect saved cluster/topic identity and the source's
persisted consumer-group offsets. They never join the group, fetch messages,
seek, commit or reset offsets. Inactive, unpublished and retired sources remain
eligible for verification. Prepared/scheduled historical records use their frozen
runtime credential when the subscription now references another credential.
Required broker permissions include source metadata, group-coordinator discovery
and committed-offset reads.

Uncertain or mismatched source identity, missing offsets, unresolved partition
gaps, unavailable credentials, broker errors and content gates retain evidence.
Source identity follows the existing supported/unsupported identifier rules;
cleanup does not require brokers to expose identifiers they do not support or
invent missing historical identifiers from current metadata. Expired Kafka group
offsets can prevent deletion even after minimum retention has passed.

One source client may be reused within a batch. Every record rechecks source
state, content gates and Kafka's committed offset; cleanup does not cache group
checkpoints. A changed source evidence revision forces a new source check. The
client closes when the batch ends. Subscription lifecycle locks serialize
eligibility and deletion with partition recovery tokens, recorded partition gaps
and durable content-error gates. Cleanup rechecks gaps under these locks after
the broker call, including gaps recorded before a recovery token exists.
No database transaction spans a broker call. Multiple replicas may repeat checks;
only a still-eligible row can be deleted under its database locks.

Current fixed bounds in `EventDeliveryDefaults` are candidate tuning:

| Control | Bound |
| --- | --- |
| Maximum records scanned per batch | 100 |
| Total batch deadline | 10 seconds |
| Per-record committed-position verification deadline | 5 seconds |
| Delay between non-empty pages | 50 ms |
| Delay after an empty sweep or closed trust gate | 30 seconds, with 10% jitter |
| Source-client close deadline | 1 second |

There is one cleanup batch at a time per worker, separate from ingestion's work
semaphore. New batches and final eligibility checks require shared database trust
and an accepting process. Shutdown fences new batches and cancels current work,
closing probe clients before process-owned database resources are released.
Cleanup errors retain evidence and retry; they do not shorten retention or bypass
capacity backpressure. Cleanup throughput and duplicate work across replicas
require workload measurement; these bounds do not establish a 500-deliveries/s
capacity guarantee.

## Dependencies, networking and lifecycle

Use the existing backend PostgreSQL settings (including database TLS), encryption
key and JWT signing keys. The encryption key must match the API's key so the
worker can decrypt existing Integration/runtime Credential secrets. Temporal uses
the existing namespace, signed client interceptor and internal mTLS configuration;
the local compose worker uses the existing development worker certificate. The
namespace must actually provide at least the guaranteed history retention; the
setting does not configure Temporal. Preserve that history for ambiguous starts.

Redis is optional for Kafka correctness: no startup/readiness dependency is placed
on it. Missed wakeups fall back to periodic database reconciliation; losing cache
entries falls back to authoritative PostgreSQL reads. An enabled terminal-proof
cache can avoid duplicate lookups only under the shared admission gate and the
validated proof, epoch, expiry and clock contracts.

Permit DNS, PostgreSQL, Temporal and optional Redis connectivity, plus **every
bootstrap and advertised broker address/port**, including addresses returned in
metadata after bootstrap. Network controls must account for all advertised
endpoints. Private broker hostnames must also be allowed by the
application's Integration SSRF policy on the API and Kafka worker.

The consumer and runtime preflight reuse that policy at the socket boundary.
Every new bootstrap, advertised-broker and coordinator connection resolves and
checks its destination, then connects to the checked IP while preserving the
original hostname for TLS verification. Reconnects repeat the checks; an earlier
successful Integration test does not authorize later addresses. A forbidden
destination remains a connection failure and cannot resolve or acknowledge a
record. Existing allowed-host exceptions apply; cloud metadata addresses remain
blocked even for allowed hostnames.

The consumer uses a small client adapter because aiokafka 0.14 has no public
connection-factory hook. Its installed-library tests cover bootstrap, broker and
coordinator connections and reconnects. Recheck this boundary when upgrading
aiokafka; do not patch its process-wide connection factory or the real event loop.

Startup uses the stable installation/deployment namespace and a fresh worker
process UUID. It registers/heartbeats membership before claiming a fair share of
active subscriptions, then reconciles authoritative configuration and starts
only locally owned consumers. Heartbeats and placement renewal run independently
of the existing 30-second reconciliation with 10% jitter. Claims, placement leases
and Kafka group assignment have separate authority and lifetime rules.

During that reconciliation, each owned subscription's supervisor rechecks the
existing `ConnectionRevision` from Integration, Credential, CredentialType and
encrypted-secret change metadata. A changed revision drains/stops that consumer
before replacing it with current connection settings. Unchanged subscriptions
keep running. Subscription/source identity, group IDs, Kafka positions,
publication revisions and actor attribution are not changed by this refresh.

Unavailable, disabled or out-of-scope resources hold the affected consumer and
are checked again on the next reconciliation. Restoring availability or changing
the connection revision permits automatic setup retry without republishing.
Unchanged failures retain their existing backoff; permanent content-error gates
remain protective. Detection follows reconciliation timing, not immediate push
notifications. Prepared deliveries retain their frozen resource bindings.
Unavailable frozen credentials or Integrations use the existing persisted
scheduling backoff and recovery scanner. Restoring those resources allows the
same Execution to resume scheduling without manual retry. Evidence mismatches
and expired acceptance history remain blocked under their existing rules.
With ingestion/recovery workers stopped, apply migration `b7e32a91c604` to make
legacy `runtime_unavailable` deliveries parked without automatic retry due again.
It preserves their frozen identity, retry budget and attempt history, and updates
the matching Execution retry timestamp. Other permanent failure codes remain
blocked. Restarted workers use the normal availability and acceptance-history
checks; the migration does not itself start a workflow or require a retry endpoint.

The internal `EventWorkerManager.ready` state follows registration and the first
successful authoritative reconciliation, including a zero target or no owned
subscriptions. Such workers remain healthy and idle while membership and
prepared recovery continue. Readiness does not wait for customer brokers; broker
failure stays within subscription retries. Deployment probe endpoints and exec
commands are deferred to M2; local compose installs no worker health probe.

For graceful scale-down, close admission/reconciliation and new placement/recovery
claims, mark membership draining, and keep heartbeats and owned-lease renewals
running while consumers and prepared work drain. Confirm consumer stop before
owner-checked placement release; then stop heartbeat/renewal tasks and shared
clients. If cleanup cannot confirm stop/release, retain unresolved evidence and
let peers observe lease/membership expiry. Never clear a live owner's lease to
speed up failover. Crash takeover also waits for expiry, reconciliation/startup
and Kafka rebalance; heartbeat duration alone is not a failover-time promise.

## Sizing and rollout

With R live, non-draining workers and S active subscriptions, placement normally
runs **S consumers across the fleet**, with no worker owning more than
**ceil(S/R)** after convergence. Targets differ by at most one and sum to S:

| Subscriptions | Workers | Consumers per worker |
| ---: | ---: | --- |
| 100 | 3 | `34, 33, 33` |
| 2 | 3 | `1, 1, 0` |
| 0 | 3 | `0, 0, 0` |

This balances subscription counts, not traffic. A hot subscription must fit one
worker; extra replicas do not split it into multiple slots or spread its load.
There is no load-aware placement or autoscaling. Each consumer can open multiple
broker connections. Allow temporary takeover/drain overlap during membership
changes: placement leases are not strict execution fencing, and a new owner
still needs Kafka assignment and valid delivery claims. Budget actual owned
queues, file descriptors, TLS/SASL capacity and per-process database pools.
Processing concurrency is shared per worker, not a fleet-wide throughput guarantee.

1. Apply the additive membership/placement, delivery and initialization models
   before running code that requires them. Deploy compatible API and Temporal
   execution workers, configuration and TLS/signing/decryption material.
2. Close admission by unpublishing affected workflows through the workflow API.
   Drain and **fully stop every old all-subscription worker** before starting
   lease-based workers. Never mix these topologies during upgrade or rollback.
3. With old workers and recovery loops stopped, clear only obsolete operational
   membership/placement for this deployment as described below. Preserve source
   and group identities, saved boundaries, delivery claims and frozen Execution
   evidence. Clearing placement is not a replacement for stopping old workers.
4. Keep feature activation and terminal caching disabled until database, Kafka,
   Temporal history retention and broker egress are safe. Explicitly start the
   compatible pool using the [local example](https://github.com/syntara-orchestration/syntara/blob/devel/backend/samples/kafka/README.md), then
   reconcile state before republishing selected workflows.
5. Enable terminal caching separately, only with compatible readers/writers,
   shared trust inputs and the operational checks required for that deployment.
   Disabling it returns duplicate lookup to PostgreSQL without changing identities.

For application rollback, close admission and fully drain/stop the current pool
before changing topology or binaries. Disable caching before using readers/writers
that do not understand the proof schema/epoch; drain old cache users and rotate
the external namespace before later re-enablement. Clear only obsolete
membership/placement with all workers stopped. Retain compatible recovery and
cleanup code while unresolved, ambiguous or pending-inspection evidence exists.
Never down-migrate schemas beneath those guards or delete evidence to permit it.

See [Kafka Subscribe connection testing](event-subscription-controls.md) for the
builder's non-consuming test, and [record runner recovery](kafka-record-runner.md)
for pending-inspection rollback safeguards.

## Partition initialization and upgrade ambiguity

First activation persists the complete first verified topic partition set,
independently of the current consumer assignment. Members of that immutable set
start at the `read_committed` visible end. A partition outside the saved set starts
at its earliest retained offset, which may be nonzero, including when discovered
before first activation finishes or after a consumer pause or restart. Save initialization kind
and boundary once; retries reuse the winning saved boundary rather than selecting
a newer end or beginning. A valid Kafka group checkpoint governs normal resumption.

An established partition with a missing, expired or out-of-range checkpoint is a
recovery gap. The assigned worker automatically selects and saves the earliest
retained offset, fences conflicting work, preserves prepared Execution bindings
and confirms the Kafka reset before resuming. No manual boundary selection or
duplicate-risk acknowledgement is required. Other partitions keep their valid
checkpoints. A saved incomplete boundary lost to retention follows the same path.
Interrupted recovery reuses its saved boundary; if retention has passed that
boundary, recovery saves the new retained beginning under a new recovery revision.
Unavailable or uncertain broker observations do not authorize a reset. Source
identity conflicts and permanent content errors remain blocked. Ordinary offset
recovery preserves terminal outcomes and their original cache-proof lifetimes;
it does not require cache-epoch rotation or shorten evidence retention.

Legacy sources can lack their original saved partition set or initialization
kind. The additive migration preserves that ambiguity and existing boundaries;
it does not reconstruct history from today's metadata. An unknown old set must
remain blocked for guarded recovery or controlled source replacement when
history cannot be established. Never infer original membership from current
assignment/metadata or overwrite it to unblock a rollout. See
[initialization compatibility](eventstreams/kafka-initialization.md#historical-compatibility-and-migration).

## Cache maintenance

Redis eviction, expiry or loss alone needs neither database recovery nor a new
cache epoch: proofs miss and PostgreSQL supplies/repopulates known outcomes.
Do not change shared Redis persistence, eviction, authentication or connection
requirements for this feature. Never use `FLUSHDB` or `FLUSHALL` for Kafka
maintenance, recovery or tests against shared Redis.

Before shortening cache TTL or terminal retention, or changing the clock-skew
margin, close admission and drain/stop old consumers, cache readers/writers and
cleanup processes. Rotate the deployment-managed epoch outside PostgreSQL, then
install compatible settings on every worker and cleanup process before shorter
cleanup bounds take effect. Restart and reconcile before reopening admission.
Do not trust a local disabled flag or deletion of old keys as proof that every
old reader/writer is fenced. Old/delayed writes must stay in an unreachable old
namespace. Longer retention does not extend existing cached proofs.

## Recovering a missing consumer stop acknowledgement

A crashed process can leave its `event_subscription_runtimes` row with
`stopped=false`. A replacement process has a fresh worker UUID and cannot
acknowledge the old process's stop. Lease expiry or a missing heartbeat never
clears that evidence automatically.

For a confirmed stopped process, an administrator may use the
[targeted stop acknowledgement example](https://github.com/syntara-orchestration/syntara/blob/devel/backend/samples/kafka/acknowledge-stopped-worker.example.sql):

1. Identify the exact deployment, source and old process UUID from the runtime
   row. Close admission for the source through workflow publication controls;
   keep it closed throughout maintenance. A retired source is also eligible.
2. Verify outside Syntara that the exact old process has terminated and cannot
   resume. Prevent its restart with the old process identity. A lost connection,
   failed heartbeat, replacement consumer or expired lease is insufficient proof.
3. Wait for that process's database heartbeat and any placement lease on the
   affected subscription to expire. Do not shorten them or delete evidence to
   satisfy the checks. Set `worker_fenced=true` only after step 2 is established.
4. With the normal PostgreSQL maintenance connection, run this command from the
   repository root, using the confirmed identifiers:

   ```bash
   psql --set=ON_ERROR_STOP=on \
     --set=deployment_id="$KAFKA_DEPLOYMENT_ID" \
     --set=source_id="$KAFKA_SOURCE_ID" \
     --set=worker_id="$KAFKA_STOPPED_WORKER_ID" \
     --set=worker_fenced=true \
     --file=backend/samples/kafka/acknowledge-stopped-worker.example.sql
   ```

The statement locks workflow, subscription and source in the normal lifecycle
order, then updates only the selected runtime row. One returned row confirms the
acknowledgement. Zero rows means it was already acknowledged, no matching row
exists, or a precondition remains unmet; inspect the state before proceeding.
Repeat separately for each affected source if the process hosted several consumers.

This procedure preserves permanent-content-error flags, delivery claim tokens,
prepared Executions, partition recovery state and Kafka positions. It does not
resolve messages, bypass an Activity Log hold or establish deletion eligibility.
Continue normal delivery recovery and retention checks. Resume consumers only
with fresh process UUIDs. The script never verifies process termination itself;
that remains the administrator's responsibility.

## Recovery before reactivation

1. Close activation/admission through workflow publication controls and await
   shutdown acknowledgements. Drain and stop
   **all** old consumers, recovery loops, cache readers/writers and cleanup workers
   before restore; prepared recovery must not race database/Temporal restoration.
   Resolve missing acknowledgements from confirmed crashed processes using the
   targeted procedure above, rather than waiting for lease expiry to clear them.
2. Fence old cache users and rotate this feature's externally managed UUID epoch
   outside the PostgreSQL backup/restore domain. Do not restore or reuse the old
   epoch, mint one per process, or change the persisted installation/deployment ID.
3. Restore PostgreSQL with subscription/source identities, generations, group IDs,
   initial partition boundaries, claims, partition recovery tokens and delivery/Execution
   evidence. Preserve the credential encryption key and required signing material.
4. Clear restored operational worker membership and subscription placement for
   the affected deployment while every worker remains stopped. Clear only
   `event_consumer_workers` rows and the paired `assigned_worker_id` /
   `assignment_lease_until` fields on its subscriptions. Preserve delivery claim
   tokens, partition recovery tokens, source/group identities, initialization boundaries and
   frozen/terminal delivery/Execution evidence. This is not permission to clear
   delivery claims or operational recovery decisions. Restored runtime rows may
   also contain missing stop acknowledgements; reconcile only confirmed stopped
   participants with the targeted procedure above before reopening admission.
5. Recover Kafka with matching cluster/topic identities, partitions, retained records
   and committed consumer-group positions. Recover Temporal namespace/history and
   existing workflow IDs consistently with database Execution evidence. If the
   consistency or source history is uncertain, leave activation closed.
6. Redis proof entries may be discarded/repopulated within the feature namespace;
   preserve other features' data. A restored cache hit cannot establish database
   consistency, and no old reader/writer may remain trusted.
7. Only after PostgreSQL/Kafka/Temporal evidence is consistent, start compatible
   workers with fresh process UUIDs, the new external epoch and workflows still
   unpublished. Register/heartbeat and reconcile before republishing workflows. Prepared
   recovery runs without active consumers; it waits when the whole pool is stopped.

The [manual placement reset example](https://github.com/syntara-orchestration/syntara/blob/devel/backend/samples/kafka/reset-placement.example.sql)
is limited to step 4, also applicable to obsolete topology state during rollout.
It is never run by setup, migrations or compose. Set `KAFKA_DEPLOYMENT_ID` to the
existing persisted `Installation.id` for the affected deployment, configure the
normal PostgreSQL maintenance connection, and verify all stop/epoch prerequisites
above before an administrator runs it from the repository root:

```bash
psql --set=ON_ERROR_STOP=on --set=deployment_id="$KAFKA_DEPLOYMENT_ID" \
  --file=backend/samples/kafka/reset-placement.example.sql
```

This example does not perform a restore, rotate an epoch or establish evidence
consistency. Those steps remain explicit administrator responsibilities.

Never reset/delete consumer groups, replace initial boundaries, advance offsets
manually, delete unresolved deliveries, clear claims as a shortcut, or delete
ambiguous/frozen Execution evidence to make recovery appear complete. Automatic
recovery can read only history that Kafka still retains.

## Verification boundary

Unit tests cover the existing worker composition and independent recovery,
settings, local compose defaults, disposable fixture configuration and the manual
placement reset example's deployment-scoped mutation boundary. That reset example
is not executed against PostgreSQL by these checks.
The targeted stop-acknowledgement integration tests execute its SQL statement
against PostgreSQL and cover scope, closed admission, live heartbeat/lease
refusals, explicit fencing confirmation, repeated calls and evidence preservation.
These tests cannot prove that an external process has terminated. They do not
establish live deployment, TLS/broker interoperability or restore safety.
Operator CRDs, deployment builders, reconciliation and deployment probe packaging
are deferred to M2 and are not covered by this Syntara change.
Live broker/TLS fixture matrices, CI integration/E2E provisioning, deployment smoke
runs, scale/soak measurements, backup/restore drills, full Visibility and M4 release
certification are deferred verification work and do not block this packaging story.
