# Workflow Verification and Validation

## Overview

The application implements a two-tier validation system that lets users build workflows incrementally — adding incomplete nodes, saving work-in-progress definitions, and catching errors before publishing. Validation runs at two layers: a fast client-side pass in the frontend and a comprehensive server-side pass via the backend `POST /workflows/validate` endpoint. The backend always saves workflow definitions regardless of structural validation issues, setting `has_validation_issues=true` on the record when problems are found. A workflow cannot be published until all errors and warnings are resolved.

The system is designed around three principles:

1. **Never block the author.** Users can add nodes without filling in all required fields and save at any time.
2. **Surface problems early.** A "Verify" action runs validation on demand, showing per-node error badges and a grouped validation banner.
3. **Gate publishing, not saving.** Saving with validation issues sets `has_validation_issues=true` on the workflow record. Publishing is blocked until all errors and warnings are resolved.

## Table of Contents

1. [How It Works](#how-it-works)
   - [Validation Tiers](#validation-tiers)
   - [Backend Validation Endpoint](#backend-validation-endpoint)
   - [Backend Validation Checks](#backend-validation-checks)
   - [Frontend Validation Rules](#frontend-validation-rules)
   - [Save Flow](#save-flow)
   - [Publish Gate](#publish-gate)
   - [Validation Models](#validation-models)
2. [Related Documentation](#related-documentation)

## How It Works

### Validation Tiers

```
User clicks "Verify"
  │
  ├── Tier 1: Frontend validation (instant)
  │     Runs client-side rules against the in-memory workflow graph.
  │     Catches structural issues: dangling nodes, missing connections,
  │     invalid variable references, incomplete converge nodes.
  │
  └── Tier 2: Backend validation (POST /workflows/validate)
        Runs schema version check, required fields check, JSON Schema
        validation, edge reference validation, graph cycle detection,
        orphaned node detection, converge configuration checks,
        approval configuration checks, and template expression validation.
        Returns structured per-node findings.

Both tiers always run. Frontend and backend errors are merged into
a single list for display.

A third layer — real-time connection validation (validateConnection.ts) —
runs during edge creation on the canvas. It prevents self-connections,
connections to placeholder nodes, and duplicate loop-body edges at
interaction time, before the user ever clicks Verify or Save.
```

When the user saves a workflow:

```
User clicks "Save"
  │
  └── Backend always saves the definition
        │
        ├── Runs validation via WorkflowValidator.collect_findings()
        ├── Sets has_validation_issues=true on the workflow record if errors or warnings exist
        ├── Logs a warning with user ID, error count, and finding details
        ├── Returns the saved workflow with validation_result embedded in the response
        └── Frontend displays the validation banner with per-node errors if issues were found
```

### Backend Validation Endpoint

| Endpoint | Response Model | Description |
|---|---|---|
| `POST /workflows/validate` | `ValidationResult` | Structured format with flat `findings[]` list containing severity, category, node_id, and field_path |

The endpoint accepts a `WorkflowValidateRequest` body containing a raw `workflow_definition` dict. On success it returns 200 with `ValidationResult`. If there are errors (`error_count > 0`), it raises `WorkflowDefinitionInvalidError` which returns a 422 with the validation result embedded in an RFC 9457 Problem Details response (`DetailedValidationProblemDetail`). Definitions with only warnings (no errors) return 200 — warnings do not cause a 422 here, but they do block publishing (see [Publish Gate](#publish-gate)).

The validate endpoint requires `workflow:create` permission but does not persist anything.

### Backend Validation Checks

The `WorkflowValidator` class in `syntara.workflows.validators.workflow_definition` runs these checks in order:

| Check | Category | Description |
|---|---|---|
| Schema version | `schema_version` | Rejects definitions where `schema_version` is not `2.0.0` |
| Required fields | `missing_field` | Ensures `triggers`, `nodes`, and `edges` fields exist |
| JSON Schema | `schema_violation` | Validates the full definition against the V2 JSON Schema (`workflow_definition.schema.json`). The schema defines 13+ node types via `oneOf` branches. When validation fails, the default `jsonschema` library dumps errors from all branches — useless noise. The validator identifies which node type you intended (from the `type` field), discards errors from other branches, and reports only the relevant ones (e.g., instead of 40+ errors across 13 types, you get "script node is missing `language`"). When a required object like `parameters` is missing entirely, the validator does a second pass with an empty object, re-validates, and reports what fields are missing inside it (e.g., `language` and `code` for script nodes) — giving actionable errors instead of just "something's missing." |
| Edge references | `invalid_reference` | Checks that all edge `from`/`to` IDs reference existing nodes |
| Cycle detection | `cycle_detected` | Depth-first search (DFS) over forward edges to find cycles — follows edges as deep as possible, and if it revisits a node already in the current path, that's a cycle. Feedback ports like `iterate` (the intentional back-edge on loop nodes) are excluded so loops aren't falsely flagged. |
| Orphaned nodes | `orphaned_node` | Breadth-first search (BFS) starting from all trigger nodes, fanning out level by level following edges. Any node never reached is "orphaned" — it exists on the canvas but has no path from a trigger, so it would never execute. |
| Converge config | `converge_configuration` | Validates converge nodes have ≥2 incoming branches and that `n_required` does not exceed the branch count |
| Approval configuration | `approval_configuration` | Validates approval nodes: warns when `fallback_decision` is set to `approve` without `continue_on_failure` enabled, since the fallback would have no effect. Severity: warning. |
| Template expressions | `invalid_reference` | Validates `${...}` expressions reference valid scopes (`trigger`, `workflow_context`), existing node IDs, or `loop` (only inside loop bodies). Unknown names (including `input` / `inputs` / `variables` when they are not node ids) fail the same way as a missing node. Rejects `${loop.*}` used outside loop bodies. |

Checks are ordered so that fatal structural issues (bad schema version, missing fields) short-circuit via early return before graph analysis runs. The remaining checks (schema violations, edge references, cycles, orphaned nodes, converge config, approval config, template expressions) accumulate findings without short-circuiting, and graph checks only run if the definition contains at least one node.

### Frontend Validation Rules

The frontend enforces these validation behaviors across several call sites:

| Rule | File | Called from | Description |
|---|---|---|---|
| No dangling nodes | `validateNoDanglingNodes.ts` | `validateWorkflow()` | Flags completely isolated nodes — non-trigger nodes with no incoming and no outgoing edges |
| No generic nodes | `validateNoGenericNodes.ts` | `validateWorkflow()` | Nodes with type `generic` (placeholder) are not allowed |
| Approval connections | `validateApprovalConnections.ts` | `validateWorkflow()` | Approval nodes must have proper connection structure |
| Condition connections | `validateConditionConnections.ts` | `validateWorkflow()` | Condition/switch nodes must have the Then (true) branch connected |
| Converge inputs | `validateConvergeInputs.ts` | `validateWorkflow()` | Converge nodes must not receive inputs from both branches (Then and Else) of the same condition node — that creates ambiguous execution flow |
| Loop nodes | `validateLoopNodes.ts` | `validateWorkflow()` | Loop nodes must have at least one outgoing edge from the loop body handle |
| Variable references | `validateVariableReferences.ts` | `validateWorkflow()` | `${step.field}` references must point to existing upstream nodes |
| Minimum workflow | `validateMinimumWorkflow.ts` | `useWorkflowVerification`, `useBuilderToolbarHandlers` | Workflow must have at least one trigger, one action node, and one edge connecting them |

Note: `validateBranchConnections.ts` is a shared helper used internally by `validateApprovalConnections` and `validateConditionConnections` — it is not a standalone rule in the `ERROR_RULES` array.

Frontend errors are merged with backend errors (from `POST /workflows/validate`) into a single list for display.

### Save Flow

The backend saves workflow definitions regardless of structural validation issues — validation findings never block a save. Both `POST /workflows` (create) and `PATCH /workflows/{workflow_id}` (update) follow the same pattern:

1. The backend runs `WorkflowValidator.collect_findings()` on the definition.
2. The `has_validation_issues` column on the `workflows` table is set to `true` if `error_count > 0` or `warning_count > 0`. Saves with validation issues are logged at the `WARNING` level with structured context (user ID, error count, finding details).
3. Credential scope validation (`_validate_credential_project_scope`) checks that any credentials referenced by nodes belong to a project the workflow can access. This can reject the save independently of structural validation.
4. The workflow is saved unconditionally.
5. Trigger sync (`_sync_all_trigger_types`) reconciles trigger registrations (webhooks, schedules, etc.) with the saved definition within the same transaction. If trigger sync fails (e.g., a webhook path conflict causes an `IntegrityError`), the entire transaction rolls back and the save is rejected.
6. The response includes the `validation_result` embedded in the `WorkflowRead` model.
7. The frontend displays the validation banner with per-node errors when issues are present.
8. On the next load, the frontend detects `has_validation_issues=true` and silently re-runs verification to populate the error badges.

### Publish Gate

Publishing is gated at two independent layers:

**Frontend gate.** The Publish button checks `validationErrorCount` from the Zustand workflow store. Despite the name, this counter includes all findings (errors and warnings) returned by the backend. When the count is greater than zero, the button is aria-disabled with a tooltip: "Verify your workflow before publishing — N error(s) found." When the count is zero, clicking Publish first runs `handleVerify()` as a pre-flight check — only if verification returns zero findings does it open the publish dialog.

**Backend gate.** The publish endpoint independently re-runs `WorkflowValidator.collect_findings()` and additionally checks that the workflow has at least one step (appending a `missing_field` finding if nodes are empty). It blocks if either `error_count > 0` or `warning_count > 0`, raising `WorkflowPublishValidationError`. This prevents publishing even if the frontend state is stale or bypassed.

### Validation Models

For request/response schemas and field definitions, see the OpenAPI spec for `POST /workflows/validate`. The models are defined in `syntara.workflows.models.validation_finding` (`ValidationFinding`, `ValidationResult`, `DetailedValidationProblemDetail`) and `syntara.workflows.models.workflow_validation_result` (`WorkflowValidateRequest`).

## Related Documentation

- [Workflow Definition Guide](workflow-definition-guide.md) — V2 schema structure, node types, edge format
- [Workflow Management](workflow-management.md) — CRUD operations, credential scope validation, overlapping validation coverage
- [Converge Node](converge-node.md) — converge node strategies and validation rules
- [Node Settings](node-settings.md) — retry policies and per-node configuration
- [Switch Node](switch-node.md) — condition node branching
- [Error Handling Strategy](../error-handling-strategy.md) — RFC 9457 compliance, `DetailedValidationProblemDetail` pipeline
- [Zustand Architecture](../../frontend/docs/zustand-architecture.md) — `validationErrorCount` store patterns and state management
