# Form Definitions

A form definition describes the fields and options used to collect structured input in a
workflow. [Form prompts](form-prompt-overview.md) and [form triggers](../workflow-engine/triggers/form-trigger.md)
share the form definition, field models, and validator; differences in behavior are noted below.
This guide explains how to define fields and parameters, how they are validated, and how to
extend the shared models.

## Fields

A `FormDefinition` is an ordered list of 1 to 100 fields. Each field has a unique `value_name`
that downstream steps use to read its submitted value. Fields also have a label, a required
flag, optional help and placeholder text, and a type-specific default. Definitions reject
unknown properties.

The supported field types are `text`, `textarea`, `masked_text`, `email`, `number`, `checkbox`,
`date`, `dropdown`, and `multi_select`.

`FormPromptDefinition` and `FormTriggerDefinition` both inherit from `FormDefinition`. They share
the common field models and specialize dropdown and multi-select fields to enforce their option
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

#### Form Limits

File uploads and encrypted-secret fields are not supported. `masked_text` hides a value in the
UI, but the value is stored in plain text.

## Form Parameters

Form parameters are settings on the workflow node that configure the form itself; fields inside
`form_definition` define the answers it collects.

Form prompts and form triggers use separate parameter models: `FormPromptNodeParameters` and
`FormTriggerParameters`. Both inherit `message`, `form_definition`, `submit_label`,
`success_message`, and `css_override` from `BaseFormParameters`. The prompt model additionally adds
`responder_users`, `responder_groups`, `response_window`, and `fallback_decision`.

The shared `css_override` is author-supplied CSS shown to submitters. A security validator rejects
patterns that could enable data exfiltration or code execution.

Form prompt parameters can use template expressions where supported. Form triggers run before
workflow nodes produce output, so they have no upstream values to reference and reject template
expressions throughout their parameters.

## Validation

### When saving a workflow

When a workflow is saved, each field's default is checked as if a user had submitted it. For
example, a date default must use a valid date and the form's selected components, and a dropdown
default must match one of its options.

Validation findings use `form_prompt_configuration` for form prompts and
`form_trigger_configuration` for form triggers. Drafts can be saved with findings, publishing is blocked until the findings are resolved.

### When submitting a form

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
4. **Update the JSON Schema** for each form prompt or form trigger that supports the field:
   - Form prompt: `src/syntara/schemas/workflows/v2/executors/form_prompt.schema.json`
   - Form trigger: `src/syntara/schemas/workflows/v2/triggers/form.schema.json`
5. **Add tests** for the field definition, submitted values, defaults, and options where
   applicable.

### Adding a Parameter

Put a parameter shared by form prompts and form triggers on `BaseFormParameters`. Put a
form-prompt-only parameter on `FormPromptNodeParameters` or a form-trigger-only parameter on
`FormTriggerParameters`. Update the schema for each form type that accepts the parameter; update
both for a shared parameter. Both models reject unknown properties, so the schemas must match:

- Form prompt: `src/syntara/schemas/workflows/v2/executors/form_prompt.schema.json`
- Form trigger: `src/syntara/schemas/workflows/v2/triggers/form.schema.json`

## Related Documentation

- [Form Prompt Overview](form-prompt-overview.md) — prompt runtime behavior
- [Form Trigger](../workflow-engine/triggers/form-trigger.md) — trigger runtime behavior
