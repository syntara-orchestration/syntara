# Control-plane Kafka worker operations

The Kafka pool uses the backend image and
`python -m syntara.eventstreams.consumer_entrypoint` (`start-kafka-worker` in the
container). It runs independently of API, workflow execution and background
workers. The operator's `spec.eventStreamWorker` controls enablement, replicas,
resources, pod placement and deployment safety bounds. Kafka infrastructure,
broker ACLs and broker credentials remain customer managed. The operator never
creates a deployment per subscription or per message and adds no Kafka autoscaler.

## Configuration contract

`APP_EVENTSTREAM_ENABLED` defaults to `false`. An omitted/disabled operator
configuration keeps the Kafka deployment at zero replicas. An enabled pool with
zero active subscriptions stays alive and runs prepared-delivery recovery. Setting
the entire pool to zero replicas stops both consumption and prepared recovery;
recovery waits for a compatible worker to return.

All replicas receive one explicit configuration from the Deployment template.
The Kafka deployment uses `Recreate` for configuration updates, so old and new
retention values do not coexist. Expect a temporary interruption in intake and
recovery while pods drain and are replaced. Do not patch individual pod values or
run a second Kafka deployment with different retention against the same database.

These settings are read at process/runner startup. The backend Settings defaults,
root and backend `.env.example`, compose worker and operator builder agree:

| Environment variable | Default | Operator field under `spec.eventStreamWorker` |
| --- | ---: | --- |
| `APP_EVENTSTREAM_ENABLED` | `false` | `enabled` |
| `APP_EVENT_FETCH_MAX_RECORDS` | `100` | `fetchMaxRecords` |
| `APP_EVENT_QUEUE_MAX_RECORDS` | `100` | `queueMaxRecords` |
| `APP_EVENT_QUEUE_MAX_BYTES` | `8388608` | `queueMaxBytes` |
| `APP_EVENT_PARTITION_MAX_RECORDS` | `10` | `partitionMaxRecords` |
| `APP_EVENT_PROCESSING_CONCURRENCY` | `8` | `processingConcurrency` |
| `APP_EVENT_FETCH_TIMEOUT_MS` | `100` | `fetchTimeoutMs` |
| `APP_EVENT_DRAIN_TIMEOUT_SECONDS` | `20` | `drainTimeoutSeconds` |
| `APP_EVENT_DELIVERY_RETENTION_SECONDS` | `3600` | `deliveryRetentionSeconds` |
| `APP_EVENT_TEMPORAL_HISTORY_RETENTION_SECONDS` | `86400` | `temporalHistoryRetentionSeconds` |

The operator's termination grace defaults to 60 seconds and must exceed the
configured drain deadline. Reserve extra time for hint/client/database cleanup.
When increasing compose's drain deadline, also increase `stop_grace_period`.

Queues and raw-byte bounds apply per subscription; processing concurrency is
shared across consumers and recovery in one worker. Candidate decoding limits
are `APP_EVENT_MAX_VALUE_BYTES=262144`, `APP_EVENT_MAX_ENVELOPE_BYTES=1048576` and
`APP_EVENT_MAX_HEADERS=128`. Broker fetch batches may exceed fetch byte limits;
these values are application bounds, not measured memory or throughput promises.

The following are fixed implementation bounds in `syntara.core.constants`, not
additional environment variables or CRD tuning fields:

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

## Dependencies, networking and probes

Use the existing backend PostgreSQL settings (including database TLS), encryption
key and JWT signing keys. The encryption key must match the API's key so the
worker can decrypt existing Integration/runtime Credential secrets. Temporal uses
the existing namespace, signed client interceptor and internal mTLS configuration;
the Kafka pool reuses the established worker service certificate identity. The
namespace must actually provide at least the guaranteed history retention; the
setting does not configure Temporal. Preserve that history for ambiguous starts.

Redis is optional for Kafka correctness: no startup/readiness dependency is placed
on it. Missed wakeups fall back to periodic database reconciliation; losing cache
entries cannot acknowledge or authorize a delivery.

Permit DNS, PostgreSQL, Temporal and optional Redis connectivity, plus **every
bootstrap and advertised broker address/port**, including addresses returned in
metadata after bootstrap. The operator allows Kafka worker egress because these
customer endpoints are not known from the CR. Administrators applying additional
network controls must account for all advertised endpoints. Standard Kubernetes
NetworkPolicy cannot express hostname rules; use the platform's supported egress
controls where required. Private broker hostnames must also be allowed by the
application's Integration SSRF policy on the API and Kafka worker.

The worker serves only loopback HTTP on `127.0.0.1:8091`; no Service or ingress is
created. Packaging uses Python exec probes:

```bash
python -m syntara.eventstreams.consumer_health live
python -m syntara.eventstreams.consumer_health ready
```

Readiness becomes true after the first successful authoritative reconciliation,
including an empty subscription list. It does not wait for customer broker
connections. Liveness observes the process event loop, not database, Redis,
Kafka availability, record traffic or subscription lag. Broker failure is isolated
to that subscription's retries; it must not restart unrelated workers. Readiness
closes when shutdown starts. SIGTERM closes new intake/recovery claims and drains
within the configured deadline, preserving unresolved evidence on timeout.

## Sizing and rollout

With R workers and S active subscriptions, budget approximately **R × S Kafka
consumer clients**, even when some clients have no assigned partitions. Each
client can hold several broker connections and background tasks. More replicas
than topic partitions do not increase that subscription's partition parallelism.
Budget broker connections, file descriptors, TLS/SASL load, per-subscription queues
and database pools across all R processes before manually scaling. Shared
processing limits are per process, so their pool-wide upper bound also grows with R.

1. Keep activation closed while introducing the database migrations and a backend
   image containing the completed worker and probes. Deploy compatible API and
   Temporal execution workers, then the operator schema/controller support.
2. Configure matching encryption/signing material, trusted TLS, database access,
   Temporal retention and broker egress. Keep `eventStreamWorker.enabled=false` until
   dependencies and persisted state are safe.
3. Enable the pool with administrator-selected replicas/resources. Check the
   reconciliation readiness and per-subscription controls before resuming intake.
4. For supported application rollback, pause subscriptions, wait for persisted
   worker shutdown acknowledgements, then drain/stop the pool before changing
   binaries. Keep compatible recovery/cleanup code whenever unresolved or pending
   inspection evidence exists. Do not downgrade schemas beneath their safety
   guards. Operator release downgrades remain unsupported.

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
   controls before resuming normal intake. With zero Kafka replicas this work waits.

Never reset/delete consumer groups, replace initial boundaries, advance offsets
manually, delete unresolved deliveries, clear claims as a shortcut, or delete
ambiguous/frozen Execution evidence to make recovery appear complete. Use explicit
recovery controls when retention/compaction removed a required source window.

## Verification boundary

Unit tests cover worker composition and independent recovery, probes, settings,
packaging defaults, CRD schema, builder output and operator reconciliation. They
do not establish live deployment, TLS/broker interoperability or restore safety.
Live broker/TLS fixture matrices, CI integration/E2E provisioning, deployment smoke
runs, scale/soak measurements, backup/restore drills, full Visibility and M4 release
certification are deferred verification work and do not block this packaging story.
