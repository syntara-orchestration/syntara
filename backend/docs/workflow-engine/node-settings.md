# Node Settings

## Overview

Node settings control engine-level execution behavior for individual nodes in a workflow. They are separate from node-specific parameters (which define *what* the node does) — settings define *how* the engine runs the node.

Settings are specified under the `settings` key of a node definition:

```yaml
nodes:
  - id: my_node
    type: http_request
    parameters:
      method: GET
      url: https://api.example.com/data
    settings:
      timeout: 30
      continue_on_failure: true
      retry_policy:
        max_retries: 3
```

## Settings Tiers

Not all settings apply to all node types. The available settings depend on the node type, organized into tiers:

| Tier | Fields | Node Types |
|------|--------|------------|
| **Full** | `disabled`, `continue_on_failure`, `timeout`, `retry_policy` | `http_request`, `aap_job_template`, `aap_workflow_job_template` |
| **No Retry** | `disabled`, `continue_on_failure`, `timeout` | `script`, `agentic`, `approval` |
| **COF + Disabled** | `disabled`, `continue_on_failure` | `wait` |
| **COF Only** | `continue_on_failure` | `converge`, `loop` |
| **None** | *(no settings)* | `condition`, `switch` |

Specifying a field that doesn't belong to a node's tier is a schema validation error (e.g., `retry_policy` on a `script` node).

## Fields

### `disabled`

| | |
|---|---|
| **Type** | `boolean` |
| **Default** | `null` (not disabled) |
| **Available on** | Full, No Retry, COF + Disabled tiers |
| **System default fallback** | None — `null` is treated as `false` |

When `true`, the node is skipped during execution. Downstream nodes still execute but receive no output from this node. Useful for temporarily removing a node from the flow without restructuring the graph.

```yaml
settings:
  disabled: true
```

### `continue_on_failure`

| | |
|---|---|
| **Type** | `boolean` |
| **Default** | `null` (inherits from system default) |
| **Available on** | Full, No Retry, COF + Disabled, COF Only tiers |
| **System default fallback** | `workflow_engine.continue_on_failure` catalog setting (default: `false`) |

When `true`, downstream nodes continue executing even if this node fails. The failed node's output includes `status: "failed"` and an `error` field, which downstream nodes can reference (e.g., `${failed_node.error}`).

For converge nodes specifically: when `true` and the wait duration expires before all required branches arrive, the converge proceeds with whatever branches have completed.

```yaml
settings:
  continue_on_failure: true
```

### `timeout`

| | |
|---|---|
| **Type** | `integer` (seconds, minimum 1) |
| **Default** | `null` (inherits from system default) |
| **Available on** | Full, No Retry tiers |
| **System default fallback** | Per-node-type catalog settings (see below) |

Maximum execution time in seconds. If the node hasn't completed within this window, it fails with a timeout error.

System defaults by node type:

| Node Type | Catalog Setting | Typical Default |
|-----------|----------------|-----------------|
| `script` | `workflow_engine.script_timeout_seconds` | 300 |
| `http_request` | `workflow_engine.http_request_timeout_seconds` | 30 |
| `aap_job_template` | `workflow_engine.aap_timeout_seconds` | 3600 |
| `aap_workflow_job_template` | `workflow_engine.aap_timeout_seconds` | 3600 |
| `agentic` | `workflow_engine.agentic_timeout_seconds` | 300 |

Nodes not in this table (`converge`, `loop`, `wait`, `condition`, `switch`) use dedicated config fields for timing (e.g., `wait_duration` for converge, `duration` for wait).

```yaml
settings:
  timeout: 60
```

### `retry_policy`

| | |
|---|---|
| **Type** | `object` |
| **Default** | `null` (inherits from system defaults) |
| **Available on** | Full tier only |

Controls automatic retry behavior for transient failures. See [Retry Policies](retry-policies.md) for full documentation including retryable error codes, backoff strategies, and per-node-type retry behavior.

```yaml
settings:
  retry_policy:
    max_retries: 5
    initial_interval: 2
    max_interval: 60
    backoff_coefficient: 2.0
```

**Why only Full tier?** Retry is only applicable to nodes that make HTTP requests where the engine can classify transient vs permanent errors. Other node types either handle retry internally (agentic, approval) or have no retry semantics (script, control nodes).

## Resolution Order

When a setting is not specified on a node, the engine falls back to system-wide defaults:

```
Node setting → System catalog default → Hardcoded default
```

For example, `timeout` resolution:
1. `node.settings.timeout` (if set) → use it
2. Catalog setting for the node type (e.g., `workflow_engine.script_timeout_seconds`) → use it
3. `DEFAULT_ACTIVITY_TIMEOUT_SECONDS` constant → use it

## Schema Enforcement

Settings validation happens at two layers:

1. **JSON Schema** — The workflow definition schema uses per-node-type `$ref` to enforce the correct settings tier. Invalid fields are rejected at definition time.
2. **Pydantic models** — The Python model hierarchy uses `extra="forbid"` to reject unexpected fields at parse time:

```
NodeSettingsBase
  → NodeSettingsCof (+continue_on_failure)        ← converge, loop
    → NodeSettingsCofDisabled (+disabled)            ← wait
      → NodeSettingsNoRetry (+timeout)             ← script, agentic, approval
        → NodeSettingsFull (+retry_policy)          ← http_request, aap_*
```

## Examples

### HTTP request with full settings

```yaml
- id: call_api
  type: http_request
  parameters:
    method: POST
    url: https://api.example.com/submit
  settings:
    timeout: 30
    continue_on_failure: true
    retry_policy:
      max_retries: 3
      backoff_coefficient: 2.0
```

### Script with timeout only

```yaml
- id: run_script
  type: script
  parameters:
    language: bash
    code: echo "hello"
  settings:
    timeout: 120
```

### Disabled node

```yaml
- id: optional_step
  type: http_request
  parameters:
    method: GET
    url: https://optional-service.example.com/check
  settings:
    disabled: true
```

### Wait node with disabled

```yaml
- id: cooldown
  type: wait
  parameters:
    duration: 60
  settings:
    disabled: true
```

Note: `wait` uses `duration` from parameters, not `timeout` from settings.

### Converge with continue on failure

```yaml
- id: sync_point
  type: converge
  parameters:
    strategy: all
    wait_duration: 300
  settings:
    continue_on_failure: true
```

## Related Documentation

- [Workflow Engine Architecture](workflow-engine-overview.md) — how resolved timeouts are applied during dispatch
- [Retry Policies](retry-policies.md) — retryable error codes, backoff strategies, per-node-type retry behavior
- [Workflow Definition Guide](workflow-definition-guide.md) — full workflow examples
- [V2 Schema](../../src/syntara/schemas/workflows/v2/workflow_definition.schema.json) — JSON schema source of truth
