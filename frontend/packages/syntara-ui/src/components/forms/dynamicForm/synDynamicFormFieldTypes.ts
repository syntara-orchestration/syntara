import type { FormField } from '@syntara/contracts'

import { FormFieldTypeEnum, type FormFieldByType } from '../../../forms'

export type DropdownFormField = FormFieldByType<'dropdown'>
export type MultiSelectFormField = FormFieldByType<'multi_select'>
export type OptionsFormField = DropdownFormField | MultiSelectFormField

export type StaticOptionsSource = Extract<OptionsFormField['options'], { source: 'static' }>
export type DynamicOptionsSource = Extract<OptionsFormField['options'], { source: 'dynamic' }>

export type DynamicOptionsFormField = OptionsFormField & { options: DynamicOptionsSource }

export function isOptionsFormField(field: FormField): field is OptionsFormField {
  return field.type === FormFieldTypeEnum.DROPDOWN || field.type === FormFieldTypeEnum.MULTI_SELECT
}
