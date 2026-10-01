import { FormFieldTypeEnum, parseFormDefinition } from '../../../forms'

const staticPriorityOptions = {
  source: 'static' as const,
  values: [
    { display_label: 'Low', value: 'low' },
    { display_label: 'High', value: 'high' },
  ],
}

export const sampleDynamicFormDefinition = parseFormDefinition({
  fields: [
    { type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name', required: true, help_text: 'Your display name' },
    { type: FormFieldTypeEnum.EMAIL, value_name: 'email', label: 'Email', placeholder: 'you@example.com' },
    {
      type: FormFieldTypeEnum.NUMBER,
      value_name: 'age',
      label: 'Age',
      default: 25,
    },
    {
      type: FormFieldTypeEnum.CHECKBOX,
      value_name: 'subscribe',
      label: 'Subscribe to updates',
      required: true,
    },
    {
      type: FormFieldTypeEnum.DATE,
      value_name: 'start_date',
      label: 'Start date',
      default: '2026-01-15',
    },
    {
      type: FormFieldTypeEnum.DROPDOWN,
      value_name: 'priority',
      label: 'Priority',
      options: staticPriorityOptions,
      required: true,
    },
    {
      type: FormFieldTypeEnum.MULTI_SELECT,
      value_name: 'tags',
      label: 'Tags',
      options: staticPriorityOptions,
    },
    {
      type: FormFieldTypeEnum.TEXTAREA,
      value_name: 'notes',
      label: 'Notes',
      placeholder: 'Optional details',
    },
    {
      type: FormFieldTypeEnum.MASKED_TEXT,
      value_name: 'token',
      label: 'API token',
    },
    {
      type: FormFieldTypeEnum.DROPDOWN,
      value_name: 'region',
      label: 'Region (dynamic)',
      options: {
        source: 'dynamic',
        expression: '${nodes.upstream.output.regions}',
        label_key: 'name',
        value_key: 'id',
      },
    },
  ],
})

export const invalidDynamicFormDefinition = parseFormDefinition({
  fields: [
    {
      type: FormFieldTypeEnum.EMAIL,
      value_name: 'broken',
      label: 'Broken default',
      default: 'not-an-email',
    },
  ],
})
