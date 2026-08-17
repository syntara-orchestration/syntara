# Workflow Engine: Retry Policies

## Overview

Retry policies control automatic retry behavior for workflow activities that fail due to transient errors. The Syntara workflow engine uses a **whitelist approach** — only specific HTTP status codes trigger retries; all other errors fail immediately.

Retry behavior varies by node type. Some nodes expose a configurable `retry_policy` in the workflow definition; others handle retry internally or have no retry at all.

## Retry Behavior by Node Type

| Node Type | Retry Policy Configurable? | Retry Mechanism | Error Domain |
|-----------|---------------------------|-----------------|--------------|
| `http_request` | Yes | Temporal-level retry on transient HTTP codes | HTTP status codes |
| `aap_job_template` | Yes | Temporal-level retry on dispatch; poll loop absorbs transient errors | HTTP status codes |
| `aap_workflow_job_template` | Yes | Same as `aap_job_template` | HTTP status codes |
| `script` | No | All errors non-retryable | Exit codes (no retry) |
| `agentic` | No | Client handles retry internally (3 attempts) | N/A |
| `approval` | No | Client handles retry internally (3 attempts) | N/A |
| Control nodes | No | No retry semantics | N/A |

## Default Retryable HTTP Status Codes

Nodes that support retry use these HTTP status codes as the default retryable set:

| Code | Name | Why Retryable |
|------|------|---------------|
| **429** | Too Many Requests | Rate limiting — retry with backoff allows the rate limit window to pass |
| **502** | Bad Gateway | Upstream server error — gateway may recover or reroute |
| **503** | Service Unavailable | Service temporarily down (maintenance, overload) — usually recovers |
| **504** | Gateway Timeout | Upstream timeout — may succeed if given more time |

### Codes NOT in Default List

| Code | Name | Why Non-Retryable |
|------|------|-------------------|
| **400** | Bad Request | Invalid request — won't succeed without fixing the request |
| **401** | Unauthorized | Authentication required — won't succeed without new credentials |
| **403** | Forbidden | Permission denied — won't succeed without fixing permissions |
| **404** | Not Found | Resource doesn't exist — won't succeed unless resource is created |
| **408** | Request Timeout | Rare in server-to-server; timeouts surface as connection errors or 504 |
| **500** | Internal Server Error | Too generic — could be a server bug (permanent) or transient; well-behaved APIs use 502/503/504 for transient failures |

## Retry Policy Configuration

Nodes that support retry (`http_request`, `aap_job_template`, `aap_workflow_job_template`) accept a `retry_policy` in the workflow definition under `settings`:

```yaml
nodes:
  - id: api_call
    type: http_request
    config:
      method: GET
      url: https://api.example.com/data
    settings:
      retry_policy:
        max_retries: 3
        backoff_coefficient: 2.0
        initial_interval: 1
        max_interval: 60
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_retries` | integer | 3 (from global settings) | Retries after initial attempt. 0 = no retry. |
| `initial_interval` | integer | 1 (from global settings) | Initial retry interval in seconds |
| `max_interval` | integer | 60 (from global settings) | Maximum retry interval in seconds |
| `backoff_coefficient` | float | 2.0 (from global settings) | Multiplier per retry. 1.0 = fixed, >1.0 = exponential |

All fields default to `None` — unset fields inherit from global operator-configured catalog values (`workflow_engine.retry_*`).

### Backoff Strategies

**Exponential (default)**: Each retry interval is multiplied by `backoff_coefficient`.

```yaml
retry_policy:
  max_retries: 5
  initial_interval: 1
  max_interval: 60
  backoff_coefficient: 2.0
# Intervals: 1s → 2s → 4s → 8s → 16s
```

**Fixed**: Set `backoff_coefficient: 1.0` for constant intervals.

```yaml
retry_policy:
  max_retries: 3
  initial_interval: 10
  backoff_coefficient: 1.0
# Intervals: 10s → 10s → 10s
```

## Node-Specific Retry Details

### http_request

Single HTTP call. Retry is handled entirely by Temporal's retry policy:
- Transient status codes (429, 502, 503, 504) → retryable
- All other errors (4xx, 500, connection errors) → non-retryable, fail immediately
- Connection-level errors (DNS, timeout, refused) → non-retryable

### aap_job_template / aap_workflow_job_template

Two-phase execution:

**Phase 1 — Dispatch (launch job):**
- Same retry classification as `http_request`: transient HTTP codes are retryable
- Connection errors → non-retryable
- Resolution lookups (template, inventory, labels, organization) also classify HTTP errors

**Phase 2 — Poll (monitor job):**
- Transient poll errors (429, 502, 503, 504, connection, timeout) are **absorbed** — the poll loop logs a warning, sleeps, and retries on the next cycle
- 404 during polling → fail immediately (job was deleted)
- Other non-transient errors (401, 403) → fail immediately
- The activity timeout is the backstop — no separate retry counter for poll failures

**Timeout messages distinguish two cases:**
- Normal timeout: "AAP job {id} timed out after {timeout}s"
- Poll-failure timeout: "AAP job {id} launched successfully but unable to determine completion status — polling failed repeatedly until timeout ({timeout}s). Last error: {error}"

### script

All script errors are non-retryable. The `retry_policy` setting is not available for script nodes.

### agentic

Retry is handled internally by the Agent Orchestrator client (3 attempts with exponential backoff). At the workflow level, all errors are non-retryable to prevent duplicate agent invocations. The `retry_policy` setting is not available.

### approval

Same as agentic — the Approvals API client handles retry internally. The `retry_policy` setting is not available.

## Node Settings Tiers

Different node types expose different settings:

| Settings tier | Fields | Applicable nodes |
|--------------|--------|-----------------|
| Full | `continue_on_failure`, `timeout`, `retry_policy` | `http_request`, `aap_job_template`, `aap_workflow_job_template` |
| No Retry | `continue_on_failure`, `timeout` | `script`, `agentic`, `approval` |
| COF Only | `continue_on_failure` | `converge`, `loop`, `wait` |
| None | — | `condition`, `switch` |

## Best Practices

1. **Use defaults** unless you have specific requirements — the global catalog values provide sensible defaults.

2. **Cap exponential backoff** with `max_interval` to prevent unbounded delays:
   ```yaml
   retry_policy:
     backoff_coefficient: 2.0
     max_interval: 300  # Never wait more than 5 minutes
   ```

3. **Disable retries for non-idempotent operations** that can't be made idempotent:
   ```yaml
   settings:
     retry_policy:
       max_retries: 0
   ```

4. **Monitor retry metrics** in production: number of retries per activity, success rate after retries.

## Related Documentation

- [Workflow Engine Architecture](workflow-engine-overview.md) — error handling and timeout margin shared by every node type
- [Workflow Definition Guide](workflow-definition-guide.md)
- [V2 Workflow Definition Schema](../../src/syntara/schemas/workflows/v2/workflow_definition.schema.json)
- [Error Handling Best Practices](error-handling.md)
