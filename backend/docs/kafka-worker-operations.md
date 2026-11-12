# Kafka worker operations

The backend image packages `start-event-stream-worker`, which execs
`python -m syntara.eventstreams.consumer_entrypoint` independently of the API and
workflow execution workers. The AO operator's optional `spec.eventStreamWorker`
requires this launcher and `syntara.eventstreams.consumer_health` in the backend
image before enablement.

Kafka workers host subscriptions; existing Temporal workers execute workflows.
The event worker uses four internal tables: subscriptions, immutable sources,
worker membership and Kafka partition initial positions. Matching messages use
the existing normal Execution model.

## Configuration contract

The worker is disabled by default. Local compose uses the `eventstream` profile
and the `start-event-stream-worker` launcher. The separate `kafka`
profile supplies an opt-in disposable broker; it does not provision customer Kafka.

Worker tuning uses the defaults defined in code. The tuning values are not
listed in environment examples or passed through local compose, and no CRD
fields are added for them. If tuning becomes necessary, use the existing
runtime settings mechanism rather than adding deployment variables.

These defaults are candidates, not measured throughput guarantees:

| Internal setting | Default |
| --- | --- |
| `eventstream_enabled` | `false` |
| `event_max_value_bytes` | `262144` |
| `event_max_envelope_bytes` | `1048576` |
| `event_max_headers` | `128` |
| `event_worker_heartbeat_interval_seconds` | `20` |
| `event_worker_liveness_seconds` | `60` |
| `event_subscription_lease_seconds` | `60` |
| `event_fetch_max_records` | `100` |
| `event_queue_max_records` | `100` |
| `event_queue_max_bytes` | `8388608` |
| `event_partition_max_records` | `10` |
| `event_processing_concurrency` | `8` |
| `event_fetch_timeout_ms` | `100` |
| `event_drain_timeout_seconds` | `20` |

`APP_EVENTSTREAM_ENABLED` remains the explicit opt-in switch for launching the
worker. It is an activation control, separate from worker tuning.

Queue and processing bounds apply per worker or consumer as documented in
settings. Inline limits include keys, duplicate headers and encoded arguments.
Keep the container stop grace longer than the drain deadline plus membership
and hint-listener shutdown time. The local compose grace is 60 seconds.

There are no event delivery-retention, terminal-cache, cache-epoch or Temporal
history-retention override settings. Temporal namespace retention and normal
Execution retention still bound duplicate protection.

## Dependencies, networking and lifecycle

PostgreSQL stores desired state and placement. Temporal stores accepted starts
and their original signed arguments. Redis sends optional reconciliation hints;
database polling remains authoritative. Kafka and Redis are not compose startup
dependencies, so a worker with no subscriptions can remain running.

Use the same signing, encryption, Temporal task queues and TLS configuration as
the existing workers. Bootstrap and advertised broker connections use the
Integration address policy. A successful connection test does not prove consumer
group authorization or access to every advertised broker.

Permit DNS, PostgreSQL, Temporal and optional Redis connectivity, plus every
bootstrap and metadata-advertised Kafka broker address and port. Private broker
hostnames also need the application's Integration SSRF allowlist. For
operator-managed deployments, `spec.integrationURLAllowedHosts` supplies
`APP_INTEGRATION_URL_ALLOWED_HOSTS` to the API and runtime workers. Include all
private bootstrap and advertised broker hostnames.

While a subscription is enabled and its placement is valid, connection and
authentication failures retry automatically with exponential backoff and jitter.
The calculated retry delay is capped at 30 seconds and has no attempt limit.
Each reconciliation reloads current Integration and Credential settings.
Corrected remote broker access can recover without republishing the workflow.

Publish to activate a listener. Unpublish or disable the workflow to stop
consumption. Remove the listener and publish the updated workflow to retire its
source. There are no separate pause, resume, retry, manual recovery or retirement
API controls. The builder retains its non-consuming Test connection button.

Shutdown closes new intake, drains admitted processing, stops Kafka clients and
releases placement after confirmed local stop. An accepted Temporal run is never
cancelled merely because persistence, shutdown or offset commit is uncertain.
Unresolved Kafka records stay uncommitted.

### Process-local probes

`EventWorkerManager.ready` follows registration, heartbeat startup and the first
successful authoritative reconciliation, including an empty subscription list or
a zero placement target. Idle workers remain running. Customer broker connection
failures stay within subscription retries and do not block readiness.

The backend image provides these exec commands:

```bash
python -m syntara.eventstreams.consumer_health live
python -m syntara.eventstreams.consumer_health ready
```

Each returns zero on success and nonzero on failure, using a fresh response from
the worker event loop at `127.0.0.1:8765`. The listener uses an internal protocol,
without an HTTP endpoint, Kubernetes Service or published container port. Probe
clients import only the Python standard library. Liveness does not query Kafka,
Redis, message traffic or subscription lag. Readiness reads the manager's current
state and closes before shutdown drain and shared-client cleanup. An exited or
stalled process cannot pass liveness through a stale health marker.

Kubernetes startup/liveness probes use `live`; readiness and the local compose
health check use `ready`. Metrics and customer-facing health presentation remain
separate Visibility concerns.

Hard deletion is allowed only for unused Kafka sources with no initialization
history or retained Executions, after the existing lifecycle and lease checks.
Once a source has initialized, its workflow and versions remain protected from
hard deletion. An expired lease cannot prove that every accepted Temporal run
has been saved as an Execution. Unpublish or remove the listener to stop intake;
this does not cancel accepted workflows.

## Sizing and rollout

Count-based placement leases each subscription to one worker. This avoids
starting one consumer for every worker/subscription pair. Kafka still owns
partition assignment inside each subscription group.

| Subscriptions | Workers | Target subscriptions per worker |
| --- | --- | --- |
| 100 | 3 | `34, 33, 33` |
| 2 | 3 | `1, 1, 0` |
| 0 | 3 | `0, 0, 0` |

Targets are counts, not workload estimates. A hot subscription stays on one
worker; uneven message rates can therefore produce uneven load. Heartbeat and
placement lease expiry use database time. A replacement consumer still relies
on Kafka assignment and stable workflow IDs during overlap.

## Partition initialization and upgrade ambiguity

The saved first partition set starts at the read-committed visible end. Added
partitions start at retained beginning. Valid group offsets govern resumption;
missing or invalid established offsets recover automatically from retained
beginning. Source recreation or unverifiable identity keeps consumption blocked.

Stop all event workers before migration `07ace57975ac`. Its guard refuses live
membership, unfinished legacy runtimes, pending position recovery, ambiguous
source history and scheduled ledger entries without matching confirmed normal
Executions. It also refuses every non-scheduled delivery, including cancelled,
filtered and rejected records: those rows may be the only evidence that no run
should start. Use the compatible version to finish safe handling of that evidence.

Populated retirement authorization, reason or completion fields also block the
upgrade. This migration does not archive those details or silently discard them.
Exclusive table locks protect the guards and schema changes in one transaction;
they do not replace the requirement to stop event workers.

The migration drops the delivery, capacity and runtime tables while retaining
normal Executions, source identities, placement fields and saved Kafka positions.
It also removes source columns used only by the old ledger/retirement machinery.
A downgrade recreates empty legacy tables and refuses retained event Executions
or live workers; it cannot rebuild removed delivery claims.

## Recovery before reactivation

After a database restore:

1. Stop every old event worker and prevent it from restarting.
2. Reconcile PostgreSQL, Kafka group offsets and retained Temporal history under
   the platform restore process. Restored Execution state alone does not prove a
   contiguous Kafka checkpoint.
3. Clear stale membership and placement only for the existing deployment UUID.
   `backend/samples/kafka/reset-placement.example.sql` is a manual example;
   it preserves sources, positions and Executions.
4. Start workers only after source identity and retained evidence are trusted.

A restart repairs an interrupted accepted handoff when the same source consumes
its uncommitted record again. Unpublished and retired sources have no independent
recovery scanner. If both Execution and Temporal evidence have expired or been
deleted, a retained Kafka record can start another workflow.

Kafka retention, compaction and group-offset retention limit recovery. Advancing
an offset cannot recover missing broker history. Recreating a local fixture
broker also recreates its source; do not treat it as the previous broker.

## Verification boundary

See [record processing](kafka-record-runner.md) and
[initialization](eventstreams/kafka-initialization.md) for the implementation
boundaries. The local fixture instructions are in
`backend/samples/kafka/README.md`. Unit adapters do not establish real broker,
database, TLS or cross-process behavior.

Probe tests cover readiness before and after empty reconciliation, shutdown,
process-local responses and exec exit codes. Packaging tests check the executable
launcher and Containerfile COPY instructions; they do not build or deploy the
backend image. Operator schema, Deployment builders and reconciliation are
verified separately in the AO operator repository. Live deployment, broker/TLS,
scale/soak and restore verification remain separate work.
