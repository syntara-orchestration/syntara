import { FormFieldTypeEnum, type FormFieldType } from '../../../forms'

export type FormFieldBuilderExamplePlaceholders = {
  placeholder: string
  helpText: string
  defaultValue: string
}

const EXAMPLES: Record<FormFieldType, FormFieldBuilderExamplePlaceholders> = {
  [FormFieldTypeEnum.TEXT]: {
    placeholder: 'e.g. Enter your full name',
    helpText: 'e.g. Use your legal name as it appears on official documents',
    defaultValue: 'e.g. Production',
  },
  [FormFieldTypeEnum.TEXTAREA]: {
    placeholder: 'e.g. Describe the issue in as much detail as possible',
    helpText: 'e.g. Include as much detail as possible',
    defaultValue: 'e.g. Quarterly release rollout',
  },
  [FormFieldTypeEnum.MASKED_TEXT]: {
    placeholder: 'e.g. Enter a masked value',
    helpText: 'e.g. Must be at least 8 characters',
    defaultValue: 'e.g. Enter a default masked value',
  },
  [FormFieldTypeEnum.EMAIL]: {
    placeholder: 'e.g. name@example.com',
    helpText: 'e.g. We will use this address to send a confirmation',
    defaultValue: 'e.g. team@example.com',
  },
  [FormFieldTypeEnum.NUMBER]: {
    placeholder: 'e.g. Enter a number',
    helpText: 'e.g. Enter a whole number between 1 and 100',
    defaultValue: 'e.g. 42',
  },
  [FormFieldTypeEnum.CHECKBOX]: {
    placeholder: 'e.g. Not used for checkbox fields',
    helpText: 'e.g. Check this box to confirm you agree',
    defaultValue: 'e.g. Use “Default to checked” below',
  },
  [FormFieldTypeEnum.DATE]: {
    placeholder: 'e.g. Select a date',
    helpText: 'e.g. Use ISO format YYYY-MM-DD',
    defaultValue: '2026-08-07',
  },
  [FormFieldTypeEnum.DROPDOWN]: {
    placeholder: 'e.g. Select an option',
    helpText: 'e.g. Choose the option that best matches your situation',
    defaultValue: 'e.g. Select a default...',
  },
  [FormFieldTypeEnum.MULTI_SELECT]: {
    placeholder: 'e.g. Select one or more options',
    helpText: 'e.g. You can select more than one option',
    defaultValue: 'e.g. Select a default...',
  },
}

export function getFormFieldBuilderExamplePlaceholders(type: FormFieldType): FormFieldBuilderExamplePlaceholders {
  return EXAMPLES[type]
}
