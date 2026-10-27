# Workflow runtime prototype

The V2 runner and its engine support now live in `syntara.workflow_runtime.engines.temporal`. Workflow resources and the remaining activity implementations stay in `syntara.workflows`. Application execution services use the relocated runner.

Approval is the first deferred domain-owned provider. Its provider constructs the approval handlers and registers request, expire, and cancel activities. Invocation now provides `invocation.execute` as a synchronous provider; it creates an invocation record and calls `InvocationExecutor` directly instead of starting a seeded Agent Execution workflow. HTTP request nodes use the small `http_request.execute` domain-owned synchronous provider as a second registration example. Script nodes use their existing workflow activity implementation. Worker startup discovers providers through the `syntara.workflow_activities` entry-point group and supplies shared infrastructure through `ActivityProviderContext`; the neutral registry does not construct domain implementations.

## Execution and completion

The neutral interfaces are `workflow_runtime.contracts`, `registry`, and `completion`. They and the approval provider import without loading Temporal. Handlers return `Completed` or `Deferred`; sync handlers run off the event loop and async handlers are awaited.

New approval nodes schedule `execute_registered_activity_v1` with a pinned name/version. The request handler calls `ApprovalService` directly. It creates the approval and commits its completion handoff together, so a worker crash after request creation does not strand an already visible request. Request retries reattach to the same execution/node/loop occurrence or return its existing decision.

An authorized single or batch decision stores the result in `runtime_activity_completions` in the same transaction as the approval decision. No HTTP callback is used for these approvals. The main worker drains this inbox and completes the original Temporal activity through the attempt's encrypted task token. References are private and checked against execution/project ownership. They never appear in approval API responses.

The completion adapter holds the `Deferred` translation, task tokens, and SDK errors. The V2 runner retains decision routing and timeout/cancellation orchestration. Cleanup handlers use approval business services directly.

## Compatibility and scope

Agentic and approval nodes now always use the registered activity wrapper. The old activity modules remain only as unregistered source during this prototype cleanup; they are not scheduled by the worker. The public V2 and approval API schemas are unchanged.

Invocation, approval, and HTTP request use the new registration path in this prototype. Script and other existing handlers retain their workflow activity implementation. The old agentic, approval, and HTTP request modules remain unregistered source during cleanup. The extracted runtime also still contains the existing application execution synchronization integration.

During validation, the invocation creation endpoints (`POST /invocations` and `POST /invocations/chat`), the approval request endpoint (`POST /approvals`), and the legacy workflow activity signal endpoint (`POST /executions/{execution_id}/activities/{activity_id}/signal`) return `503`. Approval decision endpoints remain enabled. These guards prevent accidental HTTP creation or callback paths from masking the registered activity implementation and should be removed after migration validation.

## Running and validating

Run `make install`, apply the normal backend Alembic migrations, and start the existing API and main worker entrypoints. Migration `330380b54a8b` adds the runtime completion table and a private nullable reference on approval requests.

The focused tests are:

```sh
cd backend
./tools/scripts/run-with-testcontainers.sh -- uv run pytest \
  tests/unit/workflow_runtime tests/integration/workflow_runtime
```

The integration tests use an isolated PostgreSQL database and the local `temporal` CLI dev server. A full server is needed to exercise asynchronous activity completion. The approval tests cover both approved and rejected branches through the actual V2 runner, domain service, completion inbox, and Temporal adapter.

## Prototype limits

- A delivery whose engine attempt is missing is retained as `unconfirmed`. This can mean a timeout, cancellation, or successful engine delivery followed by a lost database acknowledgement. The prototype does not automatically reconcile these receipts against engine history and never reports them as confirmed deliveries.
- Completion records have no retention job yet. Do not log or expose their encrypted engine bindings; preserve records needed by active runs.
- Cleanup keeps the existing workflow's best-effort policy. A separate cleanup reconciliation loop and independently deployed plugin packaging are follow-up work.
- A production rollout should replay representative exported workflows before removing the unregistered legacy modules.
