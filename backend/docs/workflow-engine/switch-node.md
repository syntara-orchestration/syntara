# Switch Node

## Overview

The switch node is a multi-case branching control-flow node that evaluates per-case boolean conditions and routes execution to the first matching case's port. Unlike the condition node (binary true/false), the switch node supports N output ports with independent conditions plus a default fallback.

This guide covers:
- How to configure switch nodes with multiple cases
- Per-case condition evaluation and routing
- Default port behavior when no case matches
- Accessing switch results from downstream nodes

## Table of Contents

1. [How It Works](#how-it-works)
2. [Config Reference](#config-reference)
3. [Accessing Switch Results](#accessing-switch-results)
4. [Examples](#examples)
   - [Approval Routing (3-case)](#approval-routing-3-case)
   - [Priority-Based Dispatch](#priority-based-dispatch)
   - [Default Fallback](#default-fallback)
5. [Interaction with Other Control Nodes](#interaction-with-other-control-nodes)
6. [Best Practices](#best-practices)
7. [Related Documentation](#related-documentation)

## How It Works

Each case in a switch node has three fields:
- **`port`**: The port identifier used for edge routing (e.g., `case_0`, `case_1`)
- **`label`**: A human-readable name for the case (e.g., "Approved", "Rejected")
- **`condition`**: A boolean expression evaluated at runtime using the same evaluator as condition nodes (`safe_eval_with_namespace`)

At execution time:
1. Cases are evaluated **in order** (first match wins)
2. Each case's `condition` is evaluated as a boolean expression against the full namespace (all upstream node outputs, trigger data, loop variables)
3. The first case whose condition evaluates to `True` determines the output port
4. If no case matches, execution routes to the `default_port`
5. Non-taken branches (and their downstream nodes) are marked as skipped

```yaml
nodes:
  - id: route_by_status
    name: Route by status
    type: switch
    config:
      cases:
        - port: case_0
          label: Approved
          condition: "${trigger.status} == 'approved'"
        - port: case_1
          label: Rejected
          condition: "${trigger.status} == 'rejected'"
      default_port: default
```

## Config Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `cases` | array | Yes | -- | Ordered list of cases to evaluate |
| `cases[].port` | string | Yes | -- | Port identifier for this case (used in edge `from_port`) |
| `cases[].label` | string | Yes | -- | Display label for this case |
| `cases[].condition` | string | Yes | -- | Boolean expression to evaluate |
| `default_port` | string | No | `"default"` | Port to route to when no case matches |

**Case evaluation rules:**
- Cases are evaluated in array order
- First truthy match wins — subsequent cases are not evaluated
- Empty condition strings are silently skipped
- Evaluation errors (invalid expression, missing variable) fail the activity

## Accessing Switch Results

The switch node produces a result that downstream nodes can reference via output mapping:

| Field | Type | Description |
|-------|------|-------------|
| `matched_port` | string | Port name that was selected for routing |

**Output mapping example:**

```yaml
nodes:
  - id: route_by_status
    type: switch
    config:
      cases:
        - port: case_0
          label: Approved
          condition: "${trigger.status} == 'approved'"
    outputs:
      selected_port: ${result.matched_port}
```

## Examples

### Approval Routing (3-case)

**Use case**: Route a request to different handlers based on its approval status.

**Goals**:
- Evaluate the status from a trigger payload
- Route to the appropriate handler
- Handle unexpected values via the default path

```yaml
schema_version: "2.0.0"
name: approval-routing
description: Route requests based on approval status

triggers:
  - id: trigger
    type: manual_trigger
    config: {}

nodes:
  - id: route_status
    name: Route by status
    type: switch
    config:
      cases:
        - port: case_0
          label: Approved
          condition: "${trigger.status} == 'approved'"
        - port: case_1
          label: Rejected
          condition: "${trigger.status} == 'rejected'"
        - port: case_2
          label: Escalated
          condition: "${trigger.status} == 'escalated'"
      default_port: default

  - id: handle_approved
    name: Process approval
    type: script_python
    config:
      code: |
        print("Request approved — proceeding with fulfillment")

  - id: handle_rejected
    name: Process rejection
    type: script_python
    config:
      code: |
        print("Request rejected — notifying requester")

  - id: handle_escalated
    name: Process escalation
    type: script_python
    config:
      code: |
        print("Request escalated — routing to manager")

  - id: handle_unknown
    name: Handle unknown status
    type: script_python
    config:
      code: |
        print("Unknown status — logging for review")

edges:
  - from: trigger
    to: route_status
  - from: route_status
    to: handle_approved
    from_port: case_0
  - from: route_status
    to: handle_rejected
    from_port: case_1
  - from: route_status
    to: handle_escalated
    from_port: case_2
  - from: route_status
    to: handle_unknown
    from_port: default
```

**Behavior**:
- Trigger with `status="approved"` → only `handle_approved` executes, other handlers skipped
- Trigger with `status="rejected"` → only `handle_rejected` executes
- Trigger with `status="pending"` → no case matches, `handle_unknown` executes via default port

### Priority-Based Dispatch

**Use case**: Route tasks to different queues based on numeric priority using comparison operators.

```yaml
nodes:
  - id: priority_router
    name: Route by priority
    type: switch
    config:
      cases:
        - port: case_0
          label: Critical
          condition: "${trigger.priority} >= 9"
        - port: case_1
          label: High
          condition: "${trigger.priority} >= 7"
        - port: case_2
          label: Normal
          condition: "${trigger.priority} >= 4"
      default_port: default

edges:
  - from: priority_router
    to: critical_queue
    from_port: case_0
  - from: priority_router
    to: high_queue
    from_port: case_1
  - from: priority_router
    to: normal_queue
    from_port: case_2
  - from: priority_router
    to: low_queue
    from_port: default
```

**Behavior**:
- Priority 10 → matches `case_0` (Critical), stops evaluating — does NOT also match `case_1` or `case_2`
- Priority 7 → `case_0` is False, `case_1` is True → routes to high queue
- Priority 2 → no case matches → routes to `low_queue` via default

**Key point**: First-match-wins ordering matters. Place the most restrictive conditions first.

### Default Fallback

**Use case**: Ensure unmatched values are handled gracefully.

```yaml
nodes:
  - id: type_router
    name: Route by type
    type: switch
    config:
      cases:
        - port: case_0
          label: Order
          condition: "${trigger.type} == 'order'"
        - port: case_1
          label: Return
          condition: "${trigger.type} == 'return'"
      default_port: default
```

When `trigger.type` is `"inquiry"` (not covered by any case), execution routes to the `default` port. If no edge connects to the default port, that branch of the workflow simply ends.

## Interaction with Other Control Nodes

### Switch After Condition

A switch node can appear downstream of a condition node. The condition selects a binary path, and the switch further branches within that path.

### Switch Before Converge

When multiple switch cases need to rejoin, connect their downstream paths to a converge node. The converge waits for whichever case was taken (non-taken cases are already skipped).

### Switch Inside Loop

Switch nodes work inside loop bodies. The loop context is set correctly, and case conditions can reference loop iteration variables (e.g., `${loop.current_item}`).

## Best Practices

### 1. Order Cases from Most to Least Specific

Since the switch uses first-match-wins, place the most specific conditions first. If a broader condition appears before a narrower one, the narrower case will never match.

### 2. Always Have a Default Path

Even if you believe all values are covered, connect an edge to the default port. Unexpected values at runtime will route to default instead of silently halting the workflow.

### 3. Use Descriptive Case Labels

Labels like `case_0` tell a reader nothing. Use labels that describe the routing intent: "Approved", "High Priority", "Region: EU". Labels appear in the UI and execution logs.

### 4. Keep Case Count Manageable

Switch nodes work best with 2-10 cases. If you need more than 10, consider whether a lookup table or scripted routing would be clearer.

### 5. Prefer Switch Over Chained Conditions

If you have 3+ binary conditions checking the same variable, replace them with a single switch node. It is easier to read, easier to maintain, and executes fewer nodes.

## Related Documentation

- [Workflow Engine Architecture](workflow-engine-overview.md) - Shared dispatch and data-flow mechanics
- [Workflow Definition Guide](workflow-definition-guide.md) - Complete guide to defining V2 workflows
