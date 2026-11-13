import type { FormDefinition, FormField } from '@syntara/contracts'

import { FormFieldTypeEnum, labelToValueName } from '../../../forms'
import {
  applyUiKind,
  FORM_FIELD_UI_KIND_VALUES,
  FormFieldUiKindEnum,
  type FormFieldUiKind,
  uiKindForField,
} from '../../../forms/formFieldUiKind'

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
    label_key: '',
    value_key: '',
  }
}

/**
 * Creates a new field definition with sensible defaults for the given type.
 */
export function createEmptyFormDefinition(): FormDefinition {
  return { fields: [createDefaultField()] }
}

export function createDefaultField(
  type: FormFieldUiKind = FormFieldUiKindEnum.TEXT,
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
    case FormFieldUiKindEnum.TEXT:
    case FormFieldUiKindEnum.TEXTAREA:
    case FormFieldUiKindEnum.MASKED_TEXT:
      return applyUiKind(base, type)
    case FormFieldUiKindEnum.EMAIL:
      return { ...base, type: FormFieldTypeEnum.EMAIL }
    case FormFieldUiKindEnum.NUMBER:
      return { ...base, type: FormFieldTypeEnum.NUMBER, default: null }
    case FormFieldUiKindEnum.CHECKBOX:
      return { ...base, type: FormFieldTypeEnum.CHECKBOX, default: false }
    case FormFieldUiKindEnum.DATE:
      return {
        ...base,
        type: FormFieldTypeEnum.DATE,
        default: null,
        include_date: true,
        include_time: false,
        include_timezone: false,
      }
    case FormFieldUiKindEnum.DROPDOWN:
      return {
        ...base,
        type: FormFieldTypeEnum.DROPDOWN,
        options: defaultStaticOptionsSource(),
        default: null,
      }
    case FormFieldUiKindEnum.MULTI_SELECT:
      return {
        ...base,
        type: FormFieldTypeEnum.MULTI_SELECT,
        options: defaultStaticOptionsSource(),
        default: null,
      }
    default: {
      const exhaustive: never = type
      return exhaustive
    }
  }
}

export const FORM_FIELD_TYPE_SELECT_OPTIONS = FORM_FIELD_UI_KIND_VALUES.map((value) => ({
  value,
  label: fieldTypeLabel(value),
}))

export function fieldTypeLabel(type: FormFieldUiKind): string {
  switch (type) {
    case FormFieldUiKindEnum.TEXT:
      return 'Text'
    case FormFieldUiKindEnum.TEXTAREA:
      return 'Text area'
    case FormFieldUiKindEnum.MASKED_TEXT:
      return 'Masked text'
    case FormFieldUiKindEnum.EMAIL:
      return 'Email'
    case FormFieldUiKindEnum.NUMBER:
      return 'Number'
    case FormFieldUiKindEnum.CHECKBOX:
      return 'Checkbox'
    case FormFieldUiKindEnum.DATE:
      return 'Date'
    case FormFieldUiKindEnum.DROPDOWN:
      return 'Dropdown'
    case FormFieldUiKindEnum.MULTI_SELECT:
      return 'Multi-select'
    default: {
      const exhaustive: never = type
      return exhaustive
    }
  }
}

/**
 * Replaces a field with a new type while preserving shared metadata.
 */
export function replaceFieldType(
  field: FormField,
  newType: FormFieldUiKind,
  takenNames: ReadonlyArray<string>
): FormField {
  if (uiKindForField(field) === newType) {
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
