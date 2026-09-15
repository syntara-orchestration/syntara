# Runtime execute denials (deferred)

## Status

**Not implemented in the initial node-type permissioning delivery.** Design-time read/write enforcement, admin policy templates, and workflow definition redaction shipped first.

## Intended behavior (when implemented)

- Before dispatching an executor activity, evaluate `workflow_node_type` **execute** for the **runner** (`created_by_user_id` on the execution), not the workflow author.
- On deny, fail the node with a typed `ApplicationError` that authors can handle via existing control-flow nodes (`continue_on_failure`, condition/switch), rather than failing the entire workflow by default.
- Document the output shape for permission-denied nodes in the workflow-engine guide.

## Related code (starting points)

- [`dynamic_workflow.py`](../../src/syntara/workflows/workflow_engine/dynamic_workflow.py) — node dispatch and failure handling
- [`node_type_permissions.py`](../../src/syntara/authz/node_type_permissions.py) — `is_node_type_action_allowed(..., action="execute")`
