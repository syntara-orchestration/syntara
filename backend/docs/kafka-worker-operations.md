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
restart it with one consistent value before resuming intake. Do not start a
second pool with a different retention value against the same database. Automatic
deployment rollout controls are part of the deferred M2 operator integration.

These settings are read at process/runner startup. The backend Settings defaults,
root and backend `.env.example`, and local compose worker agree:

| Environment variable | Default |
| --- | ---: |
| `APP_EVENTSTREAM_ENABLED` | `false` |
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
The proof window is capped by terminal retention; see
[record runner cache safeguards](kafka-record-runner.md#duplicate-lookup-and-shared-gates).

Local compose's `stop_grace_period` is 60 seconds, longer than the default drain
deadline of 20 seconds. Reserve extra time for hint/client/database cleanup.
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

The internal `EventWorkerManager.ready` state becomes true after registration and
the first successful authoritative reconciliation, including when it owns no subscriptions.
It does not wait for customer broker connections. Broker failures are isolated
to subscription retries. Readiness closes when shutdown starts. SIGTERM closes
new intake/recovery claims and drains within the configured deadline. Membership
heartbeats and owned placement leases continue through bounded consumer drain;
consumers stop before leases are released. Unresolved evidence is preserved on
timeout. Deployment probe endpoints and exec commands are
deferred to M2; the local compose worker does not install a health probe.

## Sizing and rollout

With R workers and S active subscriptions, PostgreSQL placement normally
distributes the S subscription consumers across the R processes. **R × S** is an
all-workers/all-subscriptions planning envelope, not the expected steady-state
client count under placement. Allow for temporary takeover/drain overlap; a lease
is not strict execution fencing. Each client can hold several broker connections
and background tasks. Budget broker connections, file descriptors, TLS/SASL load,
per-subscription queues and database pools across all R processes before scaling.
Shared processing limits are per process, so their pool-wide upper bound grows with R.

1. Keep activation closed while introducing the database migrations and a backend
   image containing the completed worker. Run compatible API and Temporal
   execution workers before starting the local Kafka worker.
2. Configure matching encryption/signing material, trusted TLS, database access,
   Temporal retention and broker egress. Keep `APP_EVENTSTREAM_ENABLED=false` until
   dependencies and persisted state are safe.
3. Explicitly enable the local worker following the [local Kafka example](../samples/kafka/README.md).
   Confirm reconciliation and review per-subscription controls before resuming intake.
4. For supported application rollback, pause subscriptions, wait for persisted
   worker shutdown acknowledgements, then drain/stop the pool before changing
   binaries. Keep compatible recovery/cleanup code whenever unresolved or pending
   inspection evidence exists. Do not downgrade schemas beneath their safety
   guards.

See [event subscription controls](event-subscription-controls.md) for revision-
checked actions and durable acknowledgements, and [record runner recovery](kafka-record-runner.md)
for pending-inspection rollback safeguards.

## Recovery before reactivation

1. Close new activation/admission. If the database is available, pause affected
   subscriptions through the revision-checked controls and wait for shutdown
   acknowledgements. Stop the entire Kafka pool before restoring infrastructure;
   prepared recovery also uses Temporal and must not race a restore.
2. Restore PostgreSQL with subscription/source identities, generations, group IDs,
   initial partition boundaries, claims, recovery holds and delivery/Execution
   evidence. Preserve the credential encryption key and required signing material.
3. Recover Kafka with matching cluster/topic identities, partitions, retained records
   and committed consumer-group positions. Recover Temporal namespace/history and
   existing workflow IDs consistently with database Execution evidence. If the
   consistency or source history is uncertain, leave activation closed.
4. Redis can be rebuilt empty. It must not be used to infer restored delivery state.
   If terminal-proof caching was enabled, coordinate a fresh externally managed
   cache epoch while all workers remain stopped before restarting against restored
   evidence. Do not reuse a pre-restore epoch or allow old writers to repopulate it.
5. Only after database, Kafka and Temporal recovery is safe, start compatible Kafka
   workers with subscriptions still paused. Prepared recovery runs independently of
   active consumers. Review unresolved evidence and use the guarded recovery
   controls before resuming normal intake. With every Kafka worker stopped this work waits.

Never reset/delete consumer groups, replace initial boundaries, advance offsets
manually, delete unresolved deliveries, clear claims as a shortcut, or delete
ambiguous/frozen Execution evidence to make recovery appear complete. Use explicit
recovery controls when retention/compaction removed a required source window.

## Verification boundary

Unit tests cover the existing worker composition and independent recovery,
settings, local compose defaults and disposable fixture configuration. They do
not establish live deployment, TLS/broker interoperability or restore safety.
Operator CRDs, deployment builders, reconciliation and deployment probe packaging
are deferred to M2 and are not covered by this Syntara change.
Live broker/TLS fixture matrices, CI integration/E2E provisioning, deployment smoke
runs, scale/soak measurements, backup/restore drills, full Visibility and M4 release
certification are deferred verification work and do not block this packaging story.
