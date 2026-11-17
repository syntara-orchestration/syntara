import { FormFieldUiKindEnum, type FormFieldUiKind } from '../../../forms/formFieldUiKind'

export type FormFieldBuilderExamplePlaceholders = {
  placeholder: string
  helpText: string
  defaultValue: string
}

const EXAMPLES: Record<FormFieldUiKind, FormFieldBuilderExamplePlaceholders> = {
  [FormFieldUiKindEnum.TEXT]: {
    placeholder: 'e.g. Enter your full name',
    helpText: 'e.g. Use your legal name as it appears on official documents',
    defaultValue: 'e.g. Production',
  },
  [FormFieldUiKindEnum.TEXTAREA]: {
    placeholder: 'e.g. Describe the issue in as much detail as possible',
    helpText: 'e.g. Include as much detail as possible',
    defaultValue: 'e.g. Quarterly release rollout',
  },
  [FormFieldUiKindEnum.MASKED_TEXT]: {
    placeholder: 'e.g. Enter a masked value',
    helpText: 'e.g. Must be at least 8 characters',
    defaultValue: 'e.g. Enter a default masked value',
  },
  [FormFieldUiKindEnum.EMAIL]: {
    placeholder: 'e.g. name@example.com',
    helpText: 'e.g. We will use this address to send a confirmation',
    defaultValue: 'e.g. team@example.com',
  },
  [FormFieldUiKindEnum.NUMBER]: {
    placeholder: 'e.g. Enter a number',
    helpText: 'e.g. Enter a whole number between 1 and 100',
    defaultValue: 'e.g. 42',
  },
  [FormFieldUiKindEnum.CHECKBOX]: {
    placeholder: 'e.g. Not used for checkbox fields',
    helpText: 'e.g. Check this box to confirm you agree',
    defaultValue: 'e.g. Use “Initially checked” below',
  },
  [FormFieldUiKindEnum.DATE]: {
    placeholder: 'e.g. Select a date',
    helpText: 'e.g. Enter the date in MM/DD/YYYY format when shown',
    defaultValue: '08/07/2026',
  },
  [FormFieldUiKindEnum.DROPDOWN]: {
    placeholder: 'e.g. Select an option',
    helpText: 'e.g. Choose the option that best matches your situation',
    defaultValue: 'e.g. Select an initial answer...',
  },
  [FormFieldUiKindEnum.MULTI_SELECT]: {
    placeholder: 'e.g. Select one or more options',
    helpText: 'e.g. You can select more than one option',
    defaultValue: 'e.g. Select initial answers...',
  },
}

export function getFormFieldBuilderExamplePlaceholders(type: FormFieldUiKind): FormFieldBuilderExamplePlaceholders {
  return EXAMPLES[type]
}
