# Form Definitions and Fields

The form definition, field models, and submission validator are shared between form prompts and
form triggers; differences are noted below. This guide explains how to define and extend forms.

## Form Definitions

A `FormDefinition` is an ordered list of 1 to 100 fields. Each field has a unique `value_name`
that downstream steps use to read its submitted value. Fields also have a label, a required
flag, optional help and placeholder text, and a type-specific default. Definitions reject
unknown properties.

The supported field types are `text`, `textarea`, `masked_text`, `email`, `number`, `checkbox`,
`date`, `dropdown`, and `multi_select`.

- Dropdown and multi-select fields can use dynamic options in form prompts; form triggers require
static options.
- The `date` field can collect a date, time, timezone, or a permitted combination. After validation, those
  components are combined into one string: an ISO 8601 date/time value, or an IANA timezone name
  when timezone is the only component.
- Forms collect structured values. File uploads and encrypted-secret fields are not supported.
`masked_text` hides a value in the UI, but the value is stored in plain text.

## Form Parameters

Form parameters are settings on the workflow node that configure the form itself; fields inside
`form_definition` define the answers it collects.

Form prompts and form triggers share `message`, `form_definition`, `submit_label`,
`success_message`, and `css_override` through `BaseFormParameters`. Form prompts also have
`responder_users`, `responder_groups`, `response_window`, and `fallback_decision`. Form prompts
use `FormPromptDefinition`; form triggers use `FormTriggerDefinition` to enforce their option
rules.

The shared `css_override` is author-supplied CSS shown to submitters. A security validator rejects
patterns that could enable data exfiltration or code execution.

Form prompt parameters can use template expressions where supported. Form triggers run before
workflow nodes produce output, so they have no upstream values to reference and reject template
expressions throughout their parameters.

## Validation

### When saving a workflow

Default form values are checked with the same coercion rules used for submitted values.

Findings use `form_prompt_configuration` for form prompts and `form_trigger_configuration` for
form triggers. Drafts can be saved with findings; `/workflows/validate` returns `422`, and
publishing returns `409`.

### When submitting a form

Both form prompts and form triggers use `validate_form_submission()` in
`forms/validators/submission.py` to check and normalize answers. Form prompts validate against
their saved form snapshots; form triggers validate against the form definition in the workflow
version.

The submission validator also applies field-specific checks: it validates email formatting and
rejects impossible calendar dates or invalid IANA timezone names.

## Adding a Field Type

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

- [Form Prompt Overview](form-prompts/form-prompt-overview.md) — prompt runtime behavior
- [Form Trigger](workflow-engine/triggers/form-trigger.md) — trigger runtime behavior
