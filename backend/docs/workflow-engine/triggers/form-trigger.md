# Form Trigger

A form trigger lets a user start a workflow by filling out and submitting a form. Downstream
nodes can reference the submitted values. Form triggers share their form definitions, field
models, and common parameters with the [form prompt step](../../form-prompts/form-prompt-overview.md),
which collects input while a workflow is running.

For the shared trigger architecture, including output mapping, namespace registration, and how the
workflow selects a trigger activity from its node type, see [Trigger System Overview](overview.md).

## Architecture

The form definition lives in the workflow version, and the UI renders it from there. There is no
separate form table, form service, or endpoint to fetch a form.
The execution stores the cleaned submission in `input_data`; the trigger activity stores its
mapped output under `response_data`.

Because a form trigger runs before an execution exists, it has no upstream output and no running
workflow to pause. The backend receives data only after a complete submission. Each accepted
submission starts an execution, with no pending form state or deadline.

## Form Definitions, Fields, and Parameters

Form definitions list the fields in a form, while form parameters configure how the form is used.

Form triggers share their form definitions, field models, and common parameters with the form prompt step type.
See [Form Definitions](../../form-definitions.md) for field types, parameter rules, and validation details.

## Submitting a Form

The forms domain owns the field models and shared submission validator; the workflows domain
owns the trigger and execution path. Before starting a workflow,
`ExecutionService.create_execution()` calls `validate_form_trigger_submission()` in
`workflows/form_trigger.py`. That function checks the trigger's form definition, then
calls `validate_form_submission()` in `forms/validators/submission.py` to validate and normalize the answers.

```mermaid
sequenceDiagram
    participant U as Submitter (UI)
    participant API as Executions API
    participant V as Form validator
    participant T as Temporal
    participant DB as PostgreSQL

    U->>API: POST /executions {workflow_id, trigger_node_id, input_data}
    API->>API: Check execution:run permission for the workflow's project
    API->>API: Resolve the trigger node
    API->>V: Validate input against form_definition
    V-->>API: Cleaned values or all field errors
    API->>T: Start OrchestratorWorkflow
    T-->>API: Accepted
    API->>DB: Create Execution record
    API-->>U: Return execution
```

An invalid submission returns `422` with all field errors and creates no execution record. For a
valid submission, validation normalizes values according to their field definitions.

The API checks the cleaned payload's size after normalization because applying field defaults can
make it larger than the JSONB limit.

### Reading submitted values

The trigger output places submitted values under `response_data`. Read a field at
`${<trigger_node_id>.response_data.<value_name>}` or
`${trigger.response_data.<value_name>}`. Use `workflow_context.execution.created_by` and
`workflow_context.execution.created_at` for the execution's creator and creation time.

### Retrying an execution

A retry reuses the original form `input_data` and workflow version, keeping the submission tied to the
form definition from the original run. The submitter does not have to fill out the form again.

## Authorization

Submitting a form starts an execution, so the user needs `execution:run` permission in the
workflow's project. Form triggers have no responder list or additional authorization check.

## Observability

The submission path emits an audit event and a latency metric. Both are best-effort: failures are
logged and swallowed so they do not prevent a submission.

- **`form_trigger_submitted` audit event:** An INFO workflow event keyed by workflow URN. It
  records the execution, trigger node, submitter, field count, and sorted field types; labels and
  submitted values are omitted.
- **Submission latency:** Measures the full create-execution interval with a monotonic clock in
  one process.

## Extending the Feature

### Adding a new field type or parameter

For steps to add a new field type or form node parameter, see
[Adding a Field Type](../../form-definitions.md#adding-a-field-type) or
[Adding a Parameter](../../form-definitions.md#adding-a-parameter).

### Adding a trigger type

The form trigger is an example of a trigger that needs its own config and validation, but no
service or database table. See [Adding a New Trigger Type](overview.md#adding-a-new-trigger-type).

## Related Documentation

- [Form Definitions](../../form-definitions.md) — field types, validation and parameters shared
  by form prompts and form triggers
- [Trigger System Overview](overview.md) — shared trigger behavior, output flow, and multi-trigger resolution  
- [Form Prompt Overview](../../form-prompts/form-prompt-overview.md) — the sibling collection
  point that pauses a running workflow
- [Manual Trigger](manual-trigger.md) — another trigger with no external state
- [Workflow Engine Architecture](../workflow-engine-overview.md) — graph execution and dispatch
