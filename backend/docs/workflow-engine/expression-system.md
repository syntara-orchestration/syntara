# Expression System

This is the reference for the `${...}` template syntax that lets nodes reference upstream output, trigger data, and loop variables. Node docs and `workflow-engine-overview.md` link here rather than restate this table — for *why* resolution happens where it does (namespace registration, deferred validation), see [Workflow Engine Architecture — Data Flow Between Nodes](workflow-engine-overview.md#data-flow-between-nodes).

## Template Syntax

```
${namespace.field.nested_field}
```

| Expression | Resolves To |
|------------|-------------|
| `${trigger.hostname}` | Trigger input field |
| `${step_1.stdout_json.result}` | Upstream node output, nested JSON |
| `${workflow_context.now}` | Current timestamp |
| `${workflow_context.today}` | Current date |
| `${loop.item}` | Current loop item, from the nearest enclosing loop (For Each) |
| `${loop.item.name}` | Field on the current loop item |
| `${loop.index}` | Current loop iteration index |

`${loop.*}` is automatically resolved to whichever loop node is the closest upstream ancestor — you don't need to know that loop's node ID.

## Available Namespaces

| Namespace | Source | Availability |
|-----------|--------|---------------|
| `trigger` | Trigger node output | All downstream nodes |
| `{node_id}` | Any upstream node's output | Nodes downstream of that node |
| `workflow_context` | Workflow metadata (`now`, `today`, execution info) | All nodes |
| `loop` | Loop iteration data (`item`, `index`), scoped to the enclosing loop | Inside a loop body only |
| `secrets` | Resolved credential values | **Not available as a namespace** — credentials are injected per-node via `credential_id` and never placed in the resolver |

There is no `input`/`inputs`/`variables` namespace. Trigger payload is `${trigger.*}` (see [Trigger System Overview](triggers/overview.md#how-trigger-output-flows-to-downstream-nodes)). Those strings are ordinary node ids: `${input.foo}` is valid only if a node is actually named `input`.

## Type Preservation

| Config Value | Resolved Value | Type |
|-------------|----------------|------|
| `"${step_1.count}"` | `42` | int (preserved) |
| `"${step_1.result}"` | `{"key": "val"}` | dict (preserved) |
| `"Host: ${step_1.host}"` | `"Host: web-01"` | string (coerced) |
| `"${a} and ${b}"` | `"true and false"` | string (coerced) |

A single full-span template preserves its original type. Multiple templates, or a template mixed with literal text, coerce everything to a string.

## Condition Evaluation

Condition and Switch nodes evaluate boolean expressions with `safe_eval_with_namespace()` (`unified_eval.py`) — an AST-based evaluator, not `eval()`. `${...}` templates are resolved first, then the resulting expression is parsed and only allowlisted AST node types are evaluated.

| Category | Operators |
|----------|-----------|
| Comparison | `==`, `!=`, `>`, `<`, `>=`, `<=` |
| Boolean | `and`, `or` |
| Unary | `not`, `-` |

```python
"${trigger.status} == 'completed'"
"${step_1.count} >= 10"
"${trigger.priority} > 5 and ${trigger.environment} == 'production'"
"not ${step_1.is_error}"
```

## Output Mapping

A node's `outputs` config is a projection/rename layer that controls which of the executor's output model fields downstream nodes can see. Each executor produces a `NodeOutput` subclass (e.g., `ScriptOutput` with `return_code`, `stdout`, `stderr`, `stdout_json`); `NodeOutput.dump(node.outputs)` applies this mapping via `apply_output_mapping()`, and the mapped result is registered in the namespace under the node's ID. This all happens before the result reaches Temporal — suppressed fields are never stored in workflow history or the database. See [Data Flow Between Nodes](workflow-engine-overview.md#data-flow-between-nodes) for the full pipeline.

| `outputs` value | Behavior |
|-----------------|----------|
| omitted / `null` | Full output passed through |
| `{}` | All output suppressed |
| `{"field": "${expression}"}` | Extract/rename specific fields |

```yaml
outputs:
  user_count: ${result.stdout_json.users}
  order_count: ${result.stdout_json.orders}
```

## Workflow-Level Inputs

Input arrives via the selected trigger — manual (`input_data` on the execution request) or webhook (request payload) — and is registered as the `trigger` namespace. See [Trigger System Overview](triggers/overview.md) for trigger selection and multi-trigger workflows.

## Security

The evaluator enforces limits defined in `unified_eval.py`: `MAX_EXPRESSION_LENGTH` (10,000 chars), `MAX_VARIABLE_NAME_LENGTH` (500 chars), `MAX_AST_DEPTH` (50), `MAX_AST_NODES` (500). It also disallows function calls, imports/module access, and attribute access beyond namespace lookup — parsing is AST-based, and only allowlisted node types are ever evaluated.

## Related Documentation

- [Workflow Engine Architecture](workflow-engine-overview.md) — why resolution happens at the workflow layer, and how it fits into the broader data-flow/validation pipeline
- [Switch Node](switch-node.md) — multi-case branching with expressions
- [Trigger System Overview](triggers/overview.md) — how trigger output populates the `trigger` namespace
- [Workflow Definition Guide](workflow-definition-guide.md) — expression usage in workflow definitions
