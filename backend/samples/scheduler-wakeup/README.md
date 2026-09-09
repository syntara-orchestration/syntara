# Scheduler wake-up PoCs

Runnable comparison harness for the Task Executor to Scheduler wake-up path.
It implements HTTP, JetStream, and Temporal notification adapters over one
PostgreSQL-backed execution store and scheduling core.

The primary design, fault matrix, and benchmark requirements are in
[`../../docs/scheduler-wakeup-poc-plan.md`](../../docs/scheduler-wakeup-poc-plan.md).

## Quick start

From `backend/`, after `make install`:

```bash
make scheduler-wakeup-poc-test ADAPTER=http RECOVERY=on
make scheduler-wakeup-poc-test ADAPTER=jetstream RECOVERY=on
make scheduler-wakeup-poc-test ADAPTER=temporal RECOVERY=on
```

Run a reproducible five-run, 100-task measurement with one command:

```bash
./run-poc.sh http
./run-poc.sh jetstream
./run-poc.sh temporal
```

The JetStream command starts and removes an ephemeral local NATS container.
Set `POC_NATS_URL` to reuse an already-running broker. Results are saved under
`artifacts/<adapter>-<id>/metrics.json`.

The checked-in harness supplies the shared execution/outbox store, fencing and
lease recovery, the three adapters, and isolated functional tests. `poc-migrate`
runs the local reference path. The remaining commands keep the interfaces in the
plan but intentionally do not claim production-like throughput evidence: that
requires the PostgreSQL and external-service environment chosen for the next
phase.

JetStream's real broker client is opt-in so the other two PoCs stay dependency
light: run `uv run --extra jetstream ...` from this directory when connecting it
to a local NATS server.
