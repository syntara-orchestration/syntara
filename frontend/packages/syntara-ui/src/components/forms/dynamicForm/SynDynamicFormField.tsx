import type { FormField } from '@syntara/contracts'

import { FormFieldTypeEnum } from '../../../forms'
import type { FormSubmissionInput } from '../../../forms'
import { FormFieldUiKindEnum, uiKindForField } from '../../../forms/formFieldUiKind'
import type { DynamicOptionsResolver } from '../SynDynamicForm.types'
import { SynTextAreaField } from '../SynTextAreaField'
import { SynTextField } from '../SynTextField'

import {
  SynDynamicFormCheckboxField,
  SynDynamicFormDateField,
  SynDynamicFormNumberField,
  SynDynamicFormOptionsField,
} from './SynDynamicFormComplexFields'

export type SynDynamicFormFieldProps = {
  field: FormField
  isDisabled?: boolean
  resolveDynamicOptions?: DynamicOptionsResolver
  textAreaControlClassName?: string
}

export function SynDynamicFormField({
  field,
  isDisabled,
  resolveDynamicOptions,
  textAreaControlClassName,
}: Readonly<SynDynamicFormFieldProps>) {
  const fieldId = `syn-dynamic-form-${field.value_name}`
  const hint = field.help_text ?? undefined
  const isRequired = Boolean(field.required)
  const placeholder = field.placeholder ?? undefined
  const uiKind = uiKindForField(field)

  switch (uiKind) {
    case FormFieldUiKindEnum.TEXT:
      return (
        <SynTextField<FormSubmissionInput>
          name={field.value_name}
          label={field.label}
          fieldId={fieldId}
          isRequired={isRequired}
          hint={hint}
          placeholder={placeholder}
          isDisabled={isDisabled}
        />
      )
    case FormFieldUiKindEnum.EMAIL:
      return (
        <SynTextField<FormSubmissionInput>
          name={field.value_name}
          label={field.label}
          fieldId={fieldId}
          type="email"
          isRequired={isRequired}
          hint={hint}
          placeholder={placeholder}
          isDisabled={isDisabled}
        />
      )
    case FormFieldUiKindEnum.MASKED_TEXT:
      return (
        <SynTextField<FormSubmissionInput>
          name={field.value_name}
          label={field.label}
          fieldId={fieldId}
          type="password"
          isRequired={isRequired}
          hint={hint}
          placeholder={placeholder}
          isDisabled={isDisabled}
        />
      )
    case FormFieldUiKindEnum.TEXTAREA:
      return (
        <SynTextAreaField<FormSubmissionInput>
          name={field.value_name}
          label={field.label}
          fieldId={fieldId}
          isRequired={isRequired}
          hint={hint}
          placeholder={placeholder}
          isDisabled={isDisabled}
          className={textAreaControlClassName}
        />
      )
    case FormFieldUiKindEnum.NUMBER:
      if (field.type !== FormFieldTypeEnum.NUMBER) {
        throw new Error('Number UI kind must map to a number field')
      }
      return (
        <SynDynamicFormNumberField
          field={field}
          fieldId={fieldId}
          hint={hint}
          isRequired={isRequired}
          isDisabled={isDisabled}
        />
      )
    case FormFieldUiKindEnum.CHECKBOX:
      if (field.type !== FormFieldTypeEnum.CHECKBOX) {
        throw new Error('Checkbox UI kind must map to a checkbox field')
      }
      return (
        <SynDynamicFormCheckboxField
          field={field}
          fieldId={fieldId}
          hint={hint}
          isRequired={isRequired}
          isDisabled={isDisabled}
        />
      )
    case FormFieldUiKindEnum.DATE:
      if (field.type !== FormFieldTypeEnum.DATE) {
        throw new Error('Date UI kind must map to a date field')
      }
      return (
        <SynDynamicFormDateField
          field={field}
          fieldId={fieldId}
          hint={hint}
          isRequired={isRequired}
          isDisabled={isDisabled}
        />
      )
    case FormFieldUiKindEnum.DROPDOWN:
      if (field.type !== FormFieldTypeEnum.DROPDOWN) {
        throw new Error('Dropdown UI kind must map to a dropdown field')
      }
      return (
        <SynDynamicFormOptionsField
          field={field}
          fieldId={fieldId}
          hint={hint}
          isRequired={isRequired}
          isMulti={false}
          isDisabled={isDisabled}
          resolveDynamicOptions={resolveDynamicOptions}
        />
      )
    case FormFieldUiKindEnum.MULTI_SELECT:
      if (field.type !== FormFieldTypeEnum.MULTI_SELECT) {
        throw new Error('Multi-select UI kind must map to a multi-select field')
      }
      return (
        <SynDynamicFormOptionsField
          field={field}
          fieldId={fieldId}
          hint={hint}
          isRequired={isRequired}
          isMulti
          isDisabled={isDisabled}
          resolveDynamicOptions={resolveDynamicOptions}
        />
      )
    default: {
      const exhaustive: never = uiKind
      return exhaustive
    }
  }
}
