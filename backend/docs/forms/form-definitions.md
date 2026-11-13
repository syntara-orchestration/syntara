# Form Definitions

A form definition describes the fields and options used to collect structured input in a
workflow. [Form prompts](form-prompt-overview.md) and [form triggers](../workflow-engine/triggers/form-trigger.md)
share the form definition, field models, and validator; differences in behavior are noted below.
This guide explains how form fields and parameters are defined, how they are validated, and how to
extend the shared models.

## Fields

A `FormDefinition` is an ordered list of 1 to 100 fields. Each field has a unique `value_name`
that downstream steps use to read its submitted value. Fields also have a label, a required
flag, optional help and placeholder text, and a type-specific default. Each field must use a
supported type and its defined settings; unknown types and extra settings are rejected. The
100-field cap is a limit for usability, not a technical requirement.

The supported field types are `text`, `email`, `number`, `checkbox`, `date`, `dropdown`, and
`multi_select`. Text fields have a UI-only `display` property: `single_line`,
`multi_line`, or `masked`. The backend preserves this rendering hint but does not interpret it.

`display: "masked"` hides the value in the UI but does not encrypt or redact its
value. For sensitive values, use the [credential system](../credential.md) and reference
credentials from supported workflow nodes.

`FormPromptDefinition` and `FormTriggerDefinition` both inherit from `FormDefinition`. They share
the common field models and specialized dropdown and multi-select fields to enforce their option
rules.

#### Dropdown and Multi-Select Options

Form prompts can use dynamic options for dropdown and multi-select fields. Form triggers require
static options because no upstream workflow nodes have run yet.

When the workflow reaches a form prompt step, the engine evaluates the dynamic expressions and
saves the resulting options with the prompt. Responders see that saved list, and submissions are
checked against the same list.

#### Date Fields

The `date` field can collect a date, time, timezone, or a permitted combination. Inputs use ISO
8601 `YYYY-MM-DD` dates, 24-hour `HH:MM` times, and IANA timezone names. The validator rejects
impossible dates and unrecognized timezones. A date and timezone can be combined only when a time
is also selected.

After validation, the selected components are normalized into one string. If the field collects
time and timezone without a date, the time string uses the timezone's standard UTC offset.

**Planned follow-up:** Align the date field's input and normalized output with JSON Schema
2020-12 and RFC 3339. The details above describe the current behavior.

## Form Parameters

Each form prompt or form trigger has a `parameters` object. `form_definition` is one of its
top-level parameters and contains the form fields users fill in. Other parameters configure the form itself, for example:

```json
{
  "parameters": {
    "message": "Tell us what happened.",
    "form_definition": {
      "fields": [{"type": "text", "value_name": "details", "label": "Details"}]
    },
    "submit_label": "Submit",
    "success_message": "Thanks for your response.",
    "css_override": ".form { color: navy; }"
  }
}
```

Form prompts and form triggers share a base parameter model. The classes `BaseFormParameters`,
`FormPromptNodeParameters`, and `FormTriggerParameters` are defined in
`src/syntara/workflows/workflow_engine/models/workflow_definition.py`. Form prompts add responder,
response-window, and fallback parameters, see
[Responders](form-prompt-overview.md#responders) and
[Timeout and Cleanup](form-prompt-overview.md#timeout-and-cleanup) for details.

The shared `css_override` is author-supplied CSS shown to submitters. A security validator rejects
patterns that could enable data exfiltration or code execution.

Form prompts allow template expressions in supported node parameters and in dynamic option
expressions inside `form_definition`. The workflow resolves dynamic options when it reaches the
prompt step. Form triggers are submitted before the workflow starts, so they have no upstream
values to reference and reject template expressions throughout their parameters.

## Validation

### When Saving a Workflow

When a workflow is saved, the form parameter models call `validate_form_definition()` in
`forms/validators/form_definition.py` to check defaults against their field rules. The workflow
validator in `workflows/validators/workflow_definition.py` reports findings under
`form_prompt_configuration` or `form_trigger_configuration`. Drafts can be saved with findings;
the validation endpoint reports them as errors, and publishing is blocked until they are resolved.

### When Submitting a Form

Both form prompts and form triggers use `validate_form_submission()` in
`forms/validators/submission.py` to check and normalize answers. A prompt submission is checked
against the form definition saved with that prompt. A trigger submission is checked against the
form definition in the workflow version selected for the execution.

The submission validator also applies field-specific checks: it validates email formatting and
rejects impossible calendar dates or invalid IANA timezone names.

## Extending Forms

### Adding a Field Type

1. **Add the field model** in `forms/models/form_fields.py` and to the `FormField` union. Add a
   field used by both form prompts and form triggers to `CommonFormField`; for a field used by
   only one, add it to `FormPromptField` or `FormTriggerField` as appropriate.
2. **Add validation and default handling** in `forms/validators/submission.py`. If the field has
   options, update option resolution and membership checks in `forms/validators/options.py`.
3. **Set the allowed option sources.** Form prompts can use static or dynamic options. Form
   triggers must use static options; their field models should override `options` with
   `StaticOptions`.
4. **Update the schemas** for each form prompt or form trigger that supports the field:
   - Shared field definitions: `src/syntara/schemas/forms/openapi.yaml` and
     `src/syntara/schemas/workflows/v2/shared-schemas.yaml`
   - Form prompt: `src/syntara/schemas/workflows/v2/executors/form_prompt.schema.json`
   - Form trigger: `src/syntara/schemas/workflows/v2/triggers/form.schema.json`
5. **Update the API contract.** Adding a field type is additive: existing form definitions
   remain valid, so it does not require a new API major version or URL. It does change the
   OpenAPI schema, so bump the affected spec's `info.version` by a minor increment and run
   `make gen-contracts` to regenerate TypeScript types. See
   [OpenAPI Spec Management](../standards/openapi-spec-management.md).
6. **Add frontend support.** Update the form builder schema and default-field setup in
   `frontend/packages/syntara-ui/src/forms/formDefinitionSchema.ts` and
   `frontend/packages/syntara-ui/src/components/forms/formFieldBuilder/createDefaultField.ts`.
   Add rendering in `frontend/packages/syntara-ui/src/components/forms/dynamicForm/SynDynamicFormField.tsx`
   and client-side validation in `frontend/packages/syntara-ui/src/forms/formSubmissionValidation.ts`
   as needed. Add field-specific editor or input components when the type needs them.
7. **Add tests** for backend validation and any frontend builder, rendering, and submission
   behavior the field introduces.

### Adding a Parameter

Put a parameter shared by form prompts and form triggers on `BaseFormParameters`. Put a
form-prompt-only parameter on `FormPromptNodeParameters` or a form-trigger-only parameter on
`FormTriggerParameters`. Update the schema for each form type that accepts the parameter; update
both for a shared parameter. Both models reject unknown properties, so the schemas must match:

- Form prompt: `src/syntara/schemas/workflows/v2/executors/form_prompt.schema.json`
- Form trigger: `src/syntara/schemas/workflows/v2/triggers/form.schema.json`

The workflow JSON Schemas are maintained separately from the Pydantic parameter models; they are
not generated from those models. `tests/unit/workflows/test_form_prompt_schema.py` and
`tests/integration/workflows/test_form_trigger_schema.py` cover representative schema cases, but
there is no comprehensive model/schema parity check. Update and test both when adding a parameter.

## Related Documentation

- [Form Prompt Overview](form-prompt-overview.md) — prompt runtime behavior
- [Form Trigger](../workflow-engine/triggers/form-trigger.md) — trigger runtime behavior
