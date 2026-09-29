import type { FormDefinition, FormField, FormFieldType } from '@syntara/contracts'

import { FORM_FIELD_TYPE_VALUES, FormFieldTypeEnum, labelToValueName } from '../../../forms'

const DEFAULT_STATIC_OPTION = {
  display_label: 'Option 1',
  value: 'option_1',
} as const

export function createDefaultStaticOption(
  optionIndex: number,
  takenValues: ReadonlyArray<string> = []
): { display_label: string; value: string } {
  const display_label = `Option ${optionIndex + 1}`
  return {
    display_label,
    value: labelToValueName(display_label, takenValues),
  }
}

export function defaultStaticOptionsSource() {
  return {
    source: 'static' as const,
    values: [DEFAULT_STATIC_OPTION],
  }
}

export function defaultDynamicOptionsSource() {
  return {
    source: 'dynamic' as const,
    expression: '',
    label_key: null,
    value_key: null,
  }
}

/**
 * Creates a new field definition with sensible defaults for the given type.
 */
export function createEmptyFormDefinition(): FormDefinition {
  return { fields: [createDefaultField()] }
}

export function createDefaultField(
  type: FormFieldType = FormFieldTypeEnum.TEXT,
  takenNames: ReadonlyArray<string> = []
): FormField {
  const label = takenNames.length === 0 ? 'Field 1' : `Field ${takenNames.length + 1}`
  const base = {
    value_name: labelToValueName(label, takenNames),
    label,
    placeholder: null as string | null,
    help_text: null as string | null,
    required: false,
  }

  switch (type) {
    case FormFieldTypeEnum.TEXT:
      return { ...base, type: FormFieldTypeEnum.TEXT }
    case FormFieldTypeEnum.TEXTAREA:
      return { ...base, type: FormFieldTypeEnum.TEXTAREA }
    case FormFieldTypeEnum.MASKED_TEXT:
      return { ...base, type: FormFieldTypeEnum.MASKED_TEXT }
    case FormFieldTypeEnum.EMAIL:
      return { ...base, type: FormFieldTypeEnum.EMAIL }
    case FormFieldTypeEnum.NUMBER:
      return { ...base, type: FormFieldTypeEnum.NUMBER, default: null }
    case FormFieldTypeEnum.CHECKBOX:
      return { ...base, type: FormFieldTypeEnum.CHECKBOX, default: false }
    case FormFieldTypeEnum.DATE:
      return { ...base, type: FormFieldTypeEnum.DATE, default: null }
    case FormFieldTypeEnum.DROPDOWN:
      return {
        ...base,
        type: FormFieldTypeEnum.DROPDOWN,
        options: defaultStaticOptionsSource(),
        default: null,
      }
    case FormFieldTypeEnum.MULTI_SELECT:
      return {
        ...base,
        type: FormFieldTypeEnum.MULTI_SELECT,
        options: defaultStaticOptionsSource(),
        default: null,
      }
    default:
      return { ...base, type: FormFieldTypeEnum.TEXT }
  }
}

export const FORM_FIELD_TYPE_SELECT_OPTIONS = FORM_FIELD_TYPE_VALUES.map((value) => ({
  value,
  label: fieldTypeLabel(value),
}))

export function fieldTypeLabel(type: FormFieldType): string {
  switch (type) {
    case FormFieldTypeEnum.TEXT:
      return 'Text'
    case FormFieldTypeEnum.TEXTAREA:
      return 'Text area'
    case FormFieldTypeEnum.MASKED_TEXT:
      return 'Masked text'
    case FormFieldTypeEnum.EMAIL:
      return 'Email'
    case FormFieldTypeEnum.NUMBER:
      return 'Number'
    case FormFieldTypeEnum.CHECKBOX:
      return 'Checkbox'
    case FormFieldTypeEnum.DATE:
      return 'Date'
    case FormFieldTypeEnum.DROPDOWN:
      return 'Dropdown'
    case FormFieldTypeEnum.MULTI_SELECT:
      return 'Multi-select'
    default:
      return type
  }
}

/**
 * Replaces a field with a new type while preserving shared metadata.
 */
export function replaceFieldType(
  field: FormField,
  newType: FormFieldType,
  takenNames: ReadonlyArray<string>
): FormField {
  if (field.type === newType) {
    return field
  }

  const preservedNames = takenNames.filter((name) => name !== field.value_name)
  const fresh = createDefaultField(newType, preservedNames)
  return {
    ...fresh,
    value_name: field.value_name,
    label: field.label,
    placeholder: field.placeholder ?? null,
    help_text: field.help_text ?? null,
    required: field.required ?? false,
  }
}
