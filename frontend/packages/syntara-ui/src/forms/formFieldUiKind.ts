import type { FormField } from '@syntara/contracts'
import { FormFieldDisplayEnum, FormFieldTypeEnum } from '@syntara/contracts'

export const FormFieldUiKindEnum = {
  TEXT: 'text',
  TEXTAREA: 'textarea',
  MASKED_TEXT: 'masked_text',
  EMAIL: 'email',
  NUMBER: 'number',
  CHECKBOX: 'checkbox',
  DATE: 'date',
  DROPDOWN: 'dropdown',
  MULTI_SELECT: 'multi_select',
} as const

export type FormFieldUiKind = (typeof FormFieldUiKindEnum)[keyof typeof FormFieldUiKindEnum]
export type TextFormFieldUiKind =
  typeof FormFieldUiKindEnum.TEXT | typeof FormFieldUiKindEnum.TEXTAREA | typeof FormFieldUiKindEnum.MASKED_TEXT

export const FORM_FIELD_UI_KIND_VALUES = Object.values(FormFieldUiKindEnum) as FormFieldUiKind[]

export function isFormFieldUiKind(value: unknown): value is FormFieldUiKind {
  return typeof value === 'string' && FORM_FIELD_UI_KIND_VALUES.some((kind) => kind === value)
}

type FormFieldBase = Pick<FormField, 'value_name' | 'label' | 'placeholder' | 'help_text' | 'required'>

export function uiKindForField(field: FormField): FormFieldUiKind {
  if (field.type !== FormFieldTypeEnum.TEXT) {
    return field.type
  }

  const display = field.display ?? FormFieldDisplayEnum.SINGLE_LINE
  switch (display) {
    case FormFieldDisplayEnum.SINGLE_LINE:
      return FormFieldUiKindEnum.TEXT
    case FormFieldDisplayEnum.MULTI_LINE:
      return FormFieldUiKindEnum.TEXTAREA
    case FormFieldDisplayEnum.MASKED:
      return FormFieldUiKindEnum.MASKED_TEXT
    default: {
      const exhaustive: never = display
      return exhaustive
    }
  }
}

export function applyUiKind(base: FormFieldBase, kind: TextFormFieldUiKind): Extract<FormField, { type: 'text' }> {
  switch (kind) {
    case FormFieldUiKindEnum.TEXT:
      return { ...base, type: FormFieldTypeEnum.TEXT, display: FormFieldDisplayEnum.SINGLE_LINE }
    case FormFieldUiKindEnum.TEXTAREA:
      return { ...base, type: FormFieldTypeEnum.TEXT, display: FormFieldDisplayEnum.MULTI_LINE }
    case FormFieldUiKindEnum.MASKED_TEXT:
      return { ...base, type: FormFieldTypeEnum.TEXT, display: FormFieldDisplayEnum.MASKED }
    default: {
      const exhaustive: never = kind
      return exhaustive
    }
  }
}
