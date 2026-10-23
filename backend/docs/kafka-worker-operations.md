# Control-plane Kafka runtime configuration and local operation

The existing Kafka worker runs with
`python -m syntara.eventstreams.consumer_entrypoint`, independently of API,
workflow execution and background workers. The local compose profile runs that
entrypoint directly using the backend image. `make services-run` enables it
automatically for local development. Operator-managed Kubernetes
deployment, CRD controls, container launchers and deployment health probes are
deferred to M2. This guide covers backend configuration, local compose and runtime
recovery safeguards. Kafka infrastructure, broker ACLs and broker credentials
remain customer managed; the local broker example is disposable development data.

## Local development

After normal setup has built the backend image and applied migrations and seeders,
run this from `backend/` to start infrastructure, Temporal workers and the Kafka
consumer together:

```bash
make services-run
```

After updating this test branch, run `uv run alembic upgrade head` before starting
the API or workers. The migration history preserves the earlier test revision
`cdd536bc1946` and joins it with the parent's `52662dc0e022` revision, so existing
test databases and fresh databases can reach the same head.

The target loads the backend `.env`, explicitly enables event streams, and starts
infrastructure, Temporal workers and `kafka-worker` in one compose invocation.
Run `make eventstream-consumer-run` separately when only the consumer needs
restarting.
`make services-stop` stops the Kafka consumer along with the other services.
`make services-clean` also includes the consumer when removing service containers
and deleting the local database and Temporal data volumes. Images and build caches
are retained.
Wrap JSON arrays in `.env` in single quotes so `uv --env-file` preserves JSON
string quotes, for example `APP_INTEGRATION_URL_ALLOWED_HOSTS='["mcp-server","localhost"]'`.

The local service mounts `backend/src`. Rerun the target to load Python edits;
dependency changes still require `make build-images`. Broker addresses, runtime
credentials and broker CA certificates come from Integration/Credential records.
Makefile and documentation edits do not require an image rebuild.

## Configuration contract

`APP_EVENTSTREAM_ENABLED` defaults to `false`. Direct compose invocations require
the `kafka-worker` profile and an enabled flag; `make services-run` handles both
automatically. The local broker fixture remains opt-in through the `kafka` profile.
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
| `APP_EVENT_FETCH_MAX_RECORDS` | `100` |
| `APP_EVENT_QUEUE_MAX_RECORDS` | `100` |
| `APP_EVENT_QUEUE_MAX_BYTES` | `8388608` |
| `APP_EVENT_PARTITION_MAX_RECORDS` | `10` |
| `APP_EVENT_PROCESSING_CONCURRENCY` | `8` |
| `APP_EVENT_FETCH_TIMEOUT_MS` | `100` |
| `APP_EVENT_DRAIN_TIMEOUT_SECONDS` | `20` |
| `APP_EVENT_DELIVERY_RETENTION_SECONDS` | `3600` |
| `APP_EVENT_TEMPORAL_HISTORY_RETENTION_SECONDS` | `86400` |

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
| Redis terminal hint TTL / operation deadline | 60 seconds / 1 second |
| Prepared recovery scan interval / batch maximum | 60 seconds / 100 deliveries |
| Temporal RPC timeout / history safety margin | 10 seconds / 300 seconds |
| Capacity pause / resume thresholds | 3,000,000 / 2,500,000 retained delivery rows |

`CLAIM_RENEWAL_INTERVAL_SECONDS=20` is a declared constant, but the current worker
renews at checkpoints; it does not install a periodic 20-second renewal timer.
Changing that constant does not change runtime renewal behavior. Claim leases,
Redis cache lifetimes and terminal evidence retention are independent.

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
entries cannot acknowledge or authorize a delivery.

Permit DNS, PostgreSQL, Temporal and optional Redis connectivity, plus **every
bootstrap and advertised broker address/port**, including addresses returned in
metadata after bootstrap. Network controls must account for all advertised
endpoints. Private broker hostnames must also be allowed by the
application's Integration SSRF policy on the API and Kafka worker.

The internal `EventWorkerManager.ready` state becomes true after the first
successful authoritative reconciliation, including an empty subscription list.
It does not wait for customer broker connections. Broker failures are isolated
to subscription retries. Readiness closes when shutdown starts. SIGTERM closes
new intake/recovery claims and drains within the configured deadline, preserving
unresolved evidence on timeout. Deployment probe endpoints and exec commands are
deferred to M2; the local compose worker does not install a health probe.

## Sizing and rollout

With R workers and S active subscriptions, budget approximately **R × S Kafka
consumer clients**, even when some clients have no assigned partitions. Each
client can hold several broker connections and background tasks. More replicas
than topic partitions do not increase that subscription's partition parallelism.
Budget broker connections, file descriptors, TLS/SASL load, per-subscription queues
and database pools across all R processes before manually scaling. Shared
processing limits are per process, so their pool-wide upper bound also grows with R.

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
