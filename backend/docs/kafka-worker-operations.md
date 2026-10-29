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
For a retention change, pause subscriptions, drain and stop the whole pool, then
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
An explicitly enabled cache with missing/invalid trust inputs fails Settings
validation; leave caching disabled until those inputs can be established.
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
| Delivery claim lease | 60 seconds; token-fenced renewal at preparation/admission checkpoints |
| Prepared recovery scan interval / batch maximum | 60 seconds / 100 deliveries |
| Temporal RPC timeout / history safety margin | 10 seconds / 300 seconds |
| Capacity pause / resume thresholds | 3,000,000 / 2,500,000 retained delivery rows |

`CLAIM_RENEWAL_INTERVAL_SECONDS=20` is a declared constant, but the current worker
renews at checkpoints; it does not install a periodic 20-second renewal timer.
Changing that constant does not change runtime renewal behavior. Claim leases,
Redis cache lifetimes and terminal evidence retention are independent.
Unlike these fixed bounds, terminal-proof TTL and operation deadlines use the
cache settings above and require the external trust inputs when caching is enabled.

Terminal delivery retention is a **strictly positive minimum duration from
`resolved_at`**, not a storage cap or an automatic deletion deadline. Cleanup also
requires authoritative Kafka committed-position evidence and respects recovery
holds. Unresolved records, pending content inspection and frozen/ambiguous
Execution evidence never expire merely because the minimum duration passed.
Budget storage and monitor capacity separately. Redis is a disposable hint/cache;
PostgreSQL and Kafka positions remain authoritative.

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

Startup uses the stable installation/deployment namespace and a fresh worker
process UUID. It registers/heartbeats membership before claiming a fair share of
active subscriptions, then reconciles authoritative configuration and starts
only locally owned consumers. Heartbeats and placement renewal run independently
of the existing 30-second reconciliation with 10% jitter. Claims, placement leases
and Kafka group assignment have separate authority and lifetime rules.

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
2. Close admission and pause subscriptions through revision-checked controls.
   Drain and **fully stop every old all-subscription worker** before starting
   lease-based workers. Never mix these topologies during upgrade or rollback.
3. With old workers and recovery loops stopped, clear only obsolete operational
   membership/placement for this deployment as described below. Preserve source
   and group identities, saved boundaries, delivery claims and frozen Execution
   evidence. Clearing placement is not a replacement for stopping old workers.
4. Keep feature activation and terminal caching disabled until database, Kafka,
   Temporal history retention and broker egress are safe. Explicitly start the
   compatible pool using the [local example](https://github.com/syntara-orchestration/syntara/blob/devel/backend/samples/kafka/README.md), then
   reconcile state before resuming selected subscriptions.
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

See [event subscription controls](event-subscription-controls.md) for revision-
checked actions and durable acknowledgements, and [record runner recovery](kafka-record-runner.md)
for pending-inspection rollback safeguards.

## Partition initialization and upgrade ambiguity

First activation persists the complete first verified topic partition set,
independently of the current consumer assignment. Members of that immutable set
start at the `read_committed` visible end. A partition outside the saved set starts
at its earliest retained offset, which may be nonzero, including when discovered
before first activation finishes or after pause/restart. Save initialization kind
and boundary once; retries reuse the winning saved boundary rather than selecting
a newer end or beginning. A valid Kafka group checkpoint governs normal resumption.

An established partition with a missing, expired or out-of-range checkpoint is a
recovery gap. Do not reclassify it as newly added, fall back to its initial offset,
or automatically reset to latest. A saved incomplete boundary lost to retention
also requires explicit recovery.

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

## Recovery before reactivation

1. Close activation/admission. Where available, pause subscriptions through
   revision-checked controls and await shutdown acknowledgements. Drain and stop
   **all** old consumers, recovery loops, cache readers/writers and cleanup workers
   before restore; prepared recovery must not race database/Temporal restoration.
2. Fence old cache users and rotate this feature's externally managed UUID epoch
   outside the PostgreSQL backup/restore domain. Do not restore or reuse the old
   epoch, mint one per process, or change the persisted installation/deployment ID.
3. Restore PostgreSQL with subscription/source identities, generations, group IDs,
   initial partition boundaries, claims, recovery holds and delivery/Execution
   evidence. Preserve the credential encryption key and required signing material.
4. Clear restored operational worker membership and subscription placement for
   the affected deployment while every worker remains stopped. Clear only
   `event_consumer_workers` rows and the paired `assigned_worker_id` /
   `assignment_lease_until` fields on its subscriptions. Preserve delivery claim
   tokens, recovery holds, source/group identities, initialization boundaries and
   frozen/terminal delivery/Execution evidence. This is not permission to clear
   delivery claims or operational recovery decisions.
5. Recover Kafka with matching cluster/topic identities, partitions, retained records
   and committed consumer-group positions. Recover Temporal namespace/history and
   existing workflow IDs consistently with database Execution evidence. If the
   consistency or source history is uncertain, leave activation closed.
6. Redis proof entries may be discarded/repopulated within the feature namespace;
   preserve other features' data. A restored cache hit cannot establish database
   consistency, and no old reader/writer may remain trusted.
7. Only after PostgreSQL/Kafka/Temporal evidence is consistent, start compatible
   workers with fresh process UUIDs, the new external epoch and subscriptions still
   paused. Register/heartbeat and reconcile before reopening admission. Prepared
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
ambiguous/frozen Execution evidence to make recovery appear complete. Use explicit
recovery controls when retention/compaction removed a required source window.

## Verification boundary

Unit tests cover the existing worker composition and independent recovery,
settings, local compose defaults, disposable fixture configuration and the manual
example's deployment-scoped mutation boundary. The SQL example is not executed
against PostgreSQL by these checks. They do
not establish live deployment, TLS/broker interoperability or restore safety.
Operator CRDs, deployment builders, reconciliation and deployment probe packaging
are deferred to M2 and are not covered by this Syntara change.
Live broker/TLS fixture matrices, CI integration/E2E provisioning, deployment smoke
runs, scale/soak measurements, backup/restore drills, full Visibility and M4 release
certification are deferred verification work and do not block this packaging story.
