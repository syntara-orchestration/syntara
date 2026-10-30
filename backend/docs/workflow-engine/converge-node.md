# Converge Node

## Overview

The converge node is a synchronization point that joins parallel workflow branches before allowing downstream execution to continue. When a trigger or node has multiple outgoing edges, the downstream nodes execute concurrently. The converge node waits for those branches to finish, then lets the workflow proceed.

This guide covers:
- How to configure converge nodes with different strategies
- When to use "wait for all" vs "wait for any N"
- Timeout handling for slow branches
- Referencing branch results from downstream nodes

## Table of Contents

1. [Strategies](#strategies)
   - [Wait for All (default)](#wait-for-all-default)
   - [Wait for Any N](#wait-for-any-n)
2. [Config Reference](#config-reference)
3. [Accessing Branch Results](#accessing-branch-results)
4. [Examples](#examples)
   - [Fan-out / Fan-in (Wait for All)](#fan-out--fan-in-wait-for-all)
   - [Fastest N of M (Wait for Any)](#fastest-n-of-m-wait-for-any)
   - [Timeout with Continue](#timeout-with-continue)
5. [Interaction with Condition Nodes](#interaction-with-condition-nodes)
6. [Best Practices](#best-practices)
7. [Related Documentation](#related-documentation)

## Strategies

### Wait for All (default)

Waits for every incoming branch to complete before proceeding.

```yaml
nodes:
  - id: join_all
    name: Wait for all tasks
    type: converge
    config:
      strategy: all
```

`strategy` defaults to `"all"` if omitted. This is the simplest and most common usage.

### Wait for Any N

Waits for a specified number of incoming branches to complete. Once `n_required` branches finish, the converge fires immediately and remaining branches are cancelled.

```yaml
nodes:
  - id: join_fastest
    name: First 2 of 3
    type: converge
    config:
      strategy: any
      n_required: 2
```

**Key rules for `n_required`**:
- Required when `strategy` is `"any"`
- Must be a positive integer (>= 1)
- If it exceeds the number of reachable branches (after condition-based skipping), it is clamped to that count (equivalent to `"all"`)

**What happens to cancelled branches**: When the converge fires, any branches still running are cancelled and their status is set to `skipped`. Downstream nodes that depend exclusively on skipped branches are also skipped.

## Config Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `strategy` | `"all"` \| `"any"` | No | `"all"` | Convergence strategy |
| `n_required` | integer (>= 1) | When strategy is `"any"` | -- | Number of branches that must complete |
| `timeout` | integer | No | -- | Timeout in seconds before `on_timeout` fires |
| `on_timeout` | `"fail"` \| `"continue"` | No | `"fail"` | Behavior when timeout is reached |

## Accessing Branch Results

Downstream nodes can reference the output of any completed branch by its node ID using the standard expression syntax:

```yaml
# Reference the result of a specific branch node
${fetch_users.result}

# Reference a nested field from a branch node's output
${fetch_users.output.userData}
```

The converge node does not merge branch outputs into its own namespace. Each branch's results remain accessible by node ID throughout the rest of the workflow.

The converge node itself produces a small result that you can reference via output mapping:

| Field | Type | Description |
|-------|------|-------------|
| `branch_count` | integer | Total number of incoming branches (including skipped) |
| `completed_count` | integer | Number of branches that completed before the converge fired |
| `completed_branch_node_ids` | string[] | Node IDs of completed branches. Users can reference these nodes directly for outputs (e.g., `${task_a.result}`). |

`completed_branch_node_ids` lists only **direct predecessors** of the converge node, not every node in a branch chain. For example, if a branch contains `b1 -> b2 -> converge`, only `b2` appears in the list (since `b2` has the edge to the converge). Upstream nodes like `b1` are still accessible via expression references (e.g., `${b1.stdout}`).

For the `"all"` strategy, `completed_count` equals `branch_count`. For `"any"`, `completed_count` equals `n_required` (or more, if additional branches finished concurrently).

**Output mapping example**:

```yaml
nodes:
  - id: join_all
    type: converge
    config:
      strategy: all
    outputs:
      count: ${result.completed_count}
      branches: ${result.completed_branch_node_ids}
```

## Examples

### Fan-out / Fan-in (Wait for All)

**Use case**: Multiple data sources need to be fetched in parallel, then combined in a summary step.

**Goals**:
- Run all fetch operations concurrently to minimize total execution time
- Block the summary step until every fetch completes

```yaml
schema_version: "2.0.0"
name: parallel-fan-out-fan-in
description: Fetch data from three sources in parallel, then summarize

triggers:
  - id: trigger
    type: manual_trigger
    config: {}

nodes:
  - id: fetch_users
    name: Fetch Users
    type: script
    config:
      language: python
      code: |
        import json
        print(json.dumps({"users": 150}))

  - id: fetch_orders
    name: Fetch Orders
    type: script
    config:
      language: python
      code: |
        import json
        print(json.dumps({"orders": 42}))

  - id: fetch_inventory
    name: Fetch Inventory
    type: script
    config:
      language: python
      code: |
        import json
        print(json.dumps({"items": 300}))

  - id: join_all
    name: Wait for all fetches
    type: converge
    config:
      strategy: all

  - id: summary
    name: Build Summary
    type: script
    config:
      language: python
      code: |
        print("All data fetched, building summary")

edges:
  - from: trigger
    to: fetch_users
  - from: trigger
    to: fetch_orders
  - from: trigger
    to: fetch_inventory
  - from: fetch_users
    to: join_all
  - from: fetch_orders
    to: join_all
  - from: fetch_inventory
    to: join_all
  - from: join_all
    to: summary
```

**Behavior**:
- The trigger fans out to three parallel branches
- The converge node blocks until all three branches complete
- The `summary` node runs only after all data is available

**Key points**:
- The `strategy: all` setting (or omitting `strategy` entirely) is the right choice when every branch's result is needed downstream
- If any branch fails, the converge node fails and downstream nodes do not execute

### Fastest N of M (Wait for Any)

**Use case**: Running redundant health checks across services where passing a majority is sufficient.

**Goals**:
- Continue as soon as enough checks pass, without waiting for the slowest
- Cancel remaining checks to free resources

```yaml
schema_version: "2.0.0"
name: health-check-any-2-of-3
description: Continue after 2 of 3 health checks pass

triggers:
  - id: trigger
    type: manual_trigger
    config: {}

nodes:
  - id: check_db
    name: Check Database
    type: script
    config:
      language: python
      code: |
        import time; time.sleep(1)
        print("db healthy")

  - id: check_cache
    name: Check Cache
    type: script
    config:
      language: python
      code: |
        import time; time.sleep(2)
        print("cache healthy")

  - id: check_storage
    name: Check Storage
    type: script
    config:
      language: python
      code: |
        import time; time.sleep(30)
        print("storage healthy")

  - id: join_any_2
    name: 2 of 3 healthy
    type: converge
    config:
      strategy: any
      n_required: 2

  - id: report
    name: Report Status
    type: script
    config:
      language: python
      code: |
        print("System healthy (2+ checks passed)")

edges:
  - from: trigger
    to: check_db
  - from: trigger
    to: check_cache
  - from: trigger
    to: check_storage
  - from: check_db
    to: join_any_2
  - from: check_cache
    to: join_any_2
  - from: check_storage
    to: join_any_2
  - from: join_any_2
    to: report
```

**Behavior**:
- `check_db` (1s) and `check_cache` (2s) complete first
- The converge fires at ~2s with `n_required: 2` satisfied
- `check_storage` is cancelled and marked as `skipped`
- The `report` node runs immediately

**Key points**:
- Use `strategy: any` when partial completion is acceptable
- Cancelled branches do not produce results -- downstream nodes should only reference branches that are guaranteed to complete
- If a branch fails, it still counts toward `n_required` (the converge treats it as "done"). To detect failed branches, check the branch node's output status downstream

### Timeout with Continue

**Use case**: A slow branch should not block the workflow indefinitely. Use a timeout to proceed with partial results.

**Goals**:
- Set a deadline for branch completion
- Continue the workflow with whatever results are available when the deadline passes

```yaml
nodes:
  - id: join_with_timeout
    name: Wait with 10s timeout
    type: converge
    config:
      strategy: all
      timeout: 10
      on_timeout: continue
```

**Behavior**:
- The converge waits up to 10 seconds for all branches to complete
- If the timeout fires before all branches finish, incomplete branches are marked as `skipped` and the converge proceeds with whatever results are available
- Use `on_timeout: "fail"` (the default) to fail the workflow instead of continuing

**Key points**:
- Timeout works with both `"all"` and `"any"` strategies
- With `"any"`, the timeout fires only if fewer than `n_required` branches complete within the deadline
- When using `on_timeout: "continue"`, downstream nodes should handle the possibility that some branch results may be unavailable

## Interaction with Condition Nodes

When a converge node follows a condition node, some incoming branches may be unreachable because the condition chose a different path. The converge node detects unreachable branches automatically and does not wait for them.

For example, if a condition node routes to branch A but not branch B, and both branches feed into a converge node, the converge only waits for branch A. Branch B is marked as `skipped`.

This detection is transitive: if an unreachable branch itself has downstream nodes that feed into the converge, those are also recognized as unreachable.

For the `"any"` strategy, `n_required` is automatically clamped to the number of reachable branches. If a condition skips 2 of 5 branches and `n_required` is 4, it is clamped to 3 (the reachable count). This prevents the converge from waiting for branches that can never complete.

## Best Practices

### 1. Prefer `strategy: all` Unless You Have a Reason Not To

The `"all"` strategy is easier to reason about. Every branch completes, every result is available downstream. Use `"any"` only when you genuinely benefit from partial completion (redundant checks, racing providers, best-effort enrichment).

### 2. Set Timeouts for External Dependencies

If any branch calls an external service that could hang, add a `timeout` to the converge node. Choose `on_timeout: "continue"` when partial results are acceptable, or `on_timeout: "fail"` when all results are required.

### 3. Be Careful Referencing Results After `strategy: any`

When using `strategy: any`, only the branches listed in `completed_branch_node_ids` have results. Referencing a cancelled branch's output produces an empty value. Design downstream nodes to handle missing data, or use output mapping on the converge node to expose only the results you know exist.

### 4. Keep Branch Counts Manageable

Converge nodes work best with a moderate number of branches (2-10). If you find yourself converging dozens of branches, consider grouping related work into fewer nodes or using a loop construct.

### 5. Name Your Converge Nodes Descriptively

A converge node named `join` tells a reader nothing. Prefer names that describe the synchronization intent: `Wait for all fetches`, `2 of 3 healthy`, `Enrichment gate`.

## Related Documentation

- [Workflow Engine Architecture](workflow-engine-overview.md) - Shared dispatch and data-flow mechanics
- [Workflow Definition Guide](workflow-definition-guide.md) - Complete guide to defining V2 workflows with retry policies
- [Retry Policies](retry-policies.md) - Retry policy configuration for individual nodes
