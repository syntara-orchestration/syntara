# Approval Node Execution Pattern

This document describes how approval nodes execute within the workflow engine, including timeout resolution, signal protocol, retry configuration, and error handling.

## Approval Node Execution

Approval nodes suspend workflow execution using Temporal's async completion pattern until an external decision (approve/reject) is received via HTTP signal. The workflow creates an approval request in the database, then pauses via `workflow.execute_activity()` with `raise_complete_async()` inside the activity. The approval service sends the decision back through the workflow engine's signal endpoint, completing the activity.

### Execution Flow

1. **Request creation**: `_execute_approval_node()` calls `_prepare_approval_args()` to build context (`backend/src/syntara/workflows/workflow_engine/approval_mixin.py`)
2. **Async completion**: `workflow.execute_activity(ActivityName.APPROVAL, ...)` starts the activity (`approval_mixin.py`)
3. **Activity suspension**: `create_approval_request_activity()` creates the DB record and calls `activity.raise_complete_async()` (`backend/src/syntara/workflows/workflow_engine/activities/approval_activity.py`)
4. **External decision**: User submits decision via `PATCH /api/v1/approvals/{id}` (`backend/src/syntara/approvals/router.py`)
5. **Signal delivery**: Approval service sends decision to workflow via `POST /api/v1/executions/{execution_id}/activities/{activity_id}/signal` (`backend/src/syntara/workflows/executions_router.py`)
6. **Activity completion**: Temporal completes the async activity with signal payload
7. **Result processing**: `_execute_approval_node()` extracts decision fields and sets routing port (`approval_mixin.py`)

### Decision Routing

The approval node routes to downstream activities based on the decision:

- **approved** → follows edges from `approved` output port
- **rejected** → follows edges from `rejected` output port
- **invalid/missing decision** → **Bug**: currently routes to `rejected` port with warning (`approval_mixin.py`). Should instead raise an exception and fail the activity, letting `continue_on_failure` and `fallback_decision` determine the route

## Timeout Resolution

Timeout values are resolved in the following order (earliest match wins):

1. **Node-level**: `node.settings.timeout` (user override per node)
2. **Global catalog default**: `workflow_engine.approval_decision_window_seconds` runtime setting
3. **Hardcoded fallback**: `86400` seconds (24 hours)

Resolution is performed by `resolve_decision_window()` in `backend/src/syntara/workflows/workflow_engine/node_settings_resolver.py`. It checks the node's `decision_window` parameter first and, if not set, falls back to the `workflow_engine.approval_decision_window_seconds` runtime catalog value (default 86400).

### Temporal Timeout Margin

The workflow sets `start_to_close_timeout` to the decision window plus a 10-second margin (`_TEMPORAL_MARGIN = 10` from `dynamic_workflow.py`) to prevent races between the approval service signal and Temporal's timeout (`approval_mixin.py`). This ensures the approval service can deliver the signal right at the deadline without racing Temporal's cancellation.

## Signal Protocol

### Signal Endpoint

Decisions are delivered via:

```
POST /api/v1/executions/{execution_id}/activities/{activity_id}/signal
```

Where:
- `{execution_id}` is the workflow execution UUID
- `{activity_id}` is the approval node ID from the workflow definition

Implementation: `backend/src/syntara/workflows/executions_router.py`

### Signal Payload Structure

The signal payload contains a `signal_data` object with fields matching the approval `resultSchema`:

```json
{
  "signal_data": {
    "decision": "approved",
    "decided_by": "alice",
    "decided_at": "2024-07-10T15:30:00Z",
    "decision_notes": "Looks good"
  }
}
```

**Field Mapping**:
- `decision` (string, required): `"approved"` or `"rejected"`
- `decided_by` (string, required): Username of the approver
- `decided_at` (string, required): ISO 8601 timestamp when the decision was made
- `decision_notes` (string, optional): Approver's comments (truncated to 500 characters per `FieldLimits.DESCRIPTION_MAX_LENGTH`)

The approval service constructs this payload in `backend/src/syntara/approvals/clients/workflow_client.py`. Field names match the resultSchema exactly to avoid remapping in the workflow (`approval_mixin.py`).

## Retry Configuration

### Approval Service → Workflow Engine

The approval service retries signal delivery using exponential backoff to handle transient failures (network issues, temporary service unavailable).

**Configuration** (`backend/src/syntara/core/config/base.py`):

The `WorkflowClientSettings` class defines the following settings with their defaults:

| Setting | Default | Description |
| --- | --- | --- |
| `workflow_client_max_retries` | 5 | Maximum number of retry attempts (0 disables retries) |
| `workflow_client_initial_backoff_seconds` | 1.0 | Initial delay before first retry in seconds |
| `workflow_client_backoff_growth_factor` | 2.0 | Exponential growth factor for backoff delays (1.0 = fixed, >1.0 = exponential) |
| `workflow_client_max_backoff_seconds` | 10.0 | Maximum cap for backoff delay in seconds |
| `workflow_client_request_timeout_seconds` | 30.0 | Per-attempt timeout to prevent unbounded wait times (applies to initial + all retries) |

**Retry Attempt Count**: `max_retries = 5` means **6 total attempts** (1 initial + 5 retries).

**Exponential Backoff** (`workflow_client.py`):

The backoff delay is calculated as `base * (growth_factor ^ attempt)`, capped at `max_backoff_seconds`. With defaults (base=1.0s, growth=2.0, max=10.0s):
- Attempt 0 (initial): no delay
- Attempt 1 (retry 1): 1.0s delay
- Attempt 2 (retry 2): 2.0s delay
- Attempt 3 (retry 3): 4.0s delay
- Attempt 4 (retry 4): 8.0s delay
- Attempt 5 (retry 5): 10.0s delay (capped)

**Total retry duration** (worst case): ~25 seconds across 6 attempts.

### Workflow Engine → Activity Execution

Approval activities use the node's retry policy for Temporal activity retries (separate from signal delivery retries). By default, approval nodes use `RetryPolicy(maximum_attempts=1)` (no retries) unless overridden via `node.settings.retry_policy`.

Resolution is performed by `resolve_retry_policy()` in `backend/src/syntara/workflows/workflow_engine/node_settings_resolver.py`.

## Error Handling

### Retryable vs Non-Retryable Errors

The approval service classifies errors for retry eligibility (`workflow_client.py`):

**Retryable** (triggers retry with backoff):
- `httpx.ConnectError` — network connection failures
- `httpx.TimeoutException` — request timeouts
- HTTP 5xx status codes — server errors

**Non-Retryable** (fails immediately):
- HTTP 4xx status codes (except timeout-related) — client errors (bad request, not found, unauthorized)
- Validation errors from Pydantic

### Best-Effort Delivery

Signal delivery failures are logged but do **not** revert the approval decision in the database. Once the user submits a decision, that decision is persisted even if signal delivery fails (`workflow_client.py`):

> Per research.md, signal failures should be logged but not revert the approval decision (graceful degradation). The caller should handle exceptions and continue processing.

### Timeout Expiration

When an approval node's decision window expires (Temporal `TimeoutError`), the workflow engine executes a best-effort cleanup to mark pending approvals as expired (`approval_mixin.py`). The `_expire_approval_requests()` method schedules an `EXPIRE_APPROVAL` activity with a single attempt (no retries). If the expiration activity itself fails, the error is logged as a warning and swallowed.

The timeout is detected via an `ActivityError`/`TemporalTimeoutError` isinstance check in `_maybe_expire_approval()` (`approval_mixin.py`).

After expiration, the workflow routes based on the node's `continue_on_failure` setting and `fallback_decision` parameter (`dynamic_workflow.py`):

- If `continue_on_failure=false` (default): workflow marks node as failed and skips downstream activities
- If `continue_on_failure=true`: workflow routes to the `fallback_decision` port (`"approve"` or `"reject"`)

### Workflow Cancellation

When a workflow is cancelled (e.g., execution cancellation request), the engine executes a best-effort cleanup to cancel all pending approval requests (`approval_mixin.py`). The `_cancel_approval_requests()` method schedules a `CANCEL_APPROVAL` activity wrapped in `asyncio.shield` to prevent the cleanup from being cancelled by the already-cancelled workflow scope. If the cancellation activity itself fails, the error is logged as a warning and swallowed.

This is triggered by the `asyncio.CancelledError` exception handler in the workflow's main `run()` method (`dynamic_workflow.py`).

## Implementation Reference

**Core Files**:
- Workflow approval logic: `backend/src/syntara/workflows/workflow_engine/approval_mixin.py`
- Approval activity: `backend/src/syntara/workflows/workflow_engine/activities/approval_activity.py`
- Signal endpoint: `backend/src/syntara/workflows/executions_router.py`
- Signal client (approvals → workflow engine): `backend/src/syntara/approvals/clients/workflow_client.py`
- Approvals client (workflow engine → approvals): `backend/src/syntara/workflows/clients/approvals_client.py`
- Timeout resolution: `backend/src/syntara/workflows/workflow_engine/node_settings_resolver.py`
- Retry configuration: `backend/src/syntara/core/config/base.py`

**HTTP Bridge**: Communication between the workflow engine and the approvals service is bidirectional:

- **Approvals → Workflow Engine** (`WorkflowApiClient`): Sends decision signals via Temporal
- **Workflow Engine → Approvals** (`ApprovalsApiClient`): Creates approval requests, batch-cancels on workflow cancellation, batch-expires on timeout

**Callback Pattern**: The activity callback handler in `execution_service.py` uses a **fail-open** pattern: any non-`"failed"` status (including `"approved"`, `"rejected"`, `"completed"`) completes the async Temporal activity. The workflow routes based on the `decision` field in the signal payload, not the Temporal activity outcome.

**Related Documentation**:

- [Approval API Specification](../../src/syntara/schemas/approvals/openapi.yaml)
- [Workflow Executions API](../../src/syntara/schemas/workflows/v2/executions_openapi.yaml)
- [Approval Overview](./approval-overview.md)
- [Approval Authorization Model](./approval-authorization-model.md)
