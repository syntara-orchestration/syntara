# Execution Plane: Work Executor

The Work Executor is the entry point for work submission into the EP. The Consumer
(Syntara or AWX) calls it to create a `WorkItem` and persist it to the [`WorkStore`](work-store.md).

See [logical_components.md](logical_components.md) for how it fits into the logical decomposition of the Execution Plane service.

---

## Responsibility

Accepts a work submission from the Consumer — including a caller-generated UUID and the
work payload — validates it, and writes a `WorkItem` record to the [`WorkStore`](work-store.md) in
`PENDING` status. Returns to the Consumer immediately; execution is asynchronous.

The UUID is caller-owned. The Consumer generates it before submitting so it can track
the work item without waiting for a response.

---

## Submission interface

How the Consumer reaches the Work Executor is not settled. Options:

**Current (temporary):** AO writes directly to the [`WorkStore`](work-store.md) — bypassing any Work
Executor API and inserting `WorkItem` rows directly into Postgres, then sends a
`pg_notify` on `execution_plane_work_items` to wake the EP worker immediately rather
than waiting for the poll interval. This works for AO because it shares the database,
but it cannot extend to AWX/Controller, which cannot share a direct DB connection with EP.

**REST API (`POST /submit`):** EP exposes an HTTP endpoint. Both AO and Controller submit
work via HTTP. This fits the model of EP as an independently deployed service with its
own API surface. The ep-client library would wrap this call.

**Queue or messaging system:** Consumers push work submissions onto a queue (Redis, for
example); the EP worker pops them. Decouples submission from processing latency at the
cost of an additional dependency on the submission path.

The interface decision depends on the network topology between AO, Controller, and EP,
and whether EP is co-located or independently deployed.

Because both AO and Controller are consumers of this interface, the submission call is
likely to move into a client library for the Execution Plane. That library is not yet
designed.

---

## Validation

Currently, the Consumer writes directly to the `WorkItem` Postgres schema. The schema
itself enforces structure — a malformed payload is rejected at the DB layer. No
separate validation step exists.

Once a submission interface (REST API, queue) sits between the Consumer and the
[`WorkStore`](work-store.md), the EP receives formally unstructured data. At that point the Work Executor
must validate the payload against known bounds before persisting it: required fields,
type constraints, and size limits.

---

## Other attachments

It is not settled whether isolation policy belongs on the work item at submission time or
on the Target. The same open question may recur for other related structures — credentials,
resource constraints, routing hints. Work items may grow additional attachments and
associated model relationships as the design matures. The Work Executor is the natural
attachment point at submission time, but the shape of those attachments is not yet
planned.
