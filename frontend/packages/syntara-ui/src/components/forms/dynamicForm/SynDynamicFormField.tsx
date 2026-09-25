import type { FormField } from '@syntara/contracts'

import { FormFieldTypeEnum } from '../../../forms'
import type { FormSubmissionInput } from '../../../forms'
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
}

export function SynDynamicFormField({ field, isDisabled, resolveDynamicOptions }: Readonly<SynDynamicFormFieldProps>) {
  const fieldId = `syn-dynamic-form-${field.value_name}`
  const hint = field.help_text ?? undefined
  const isRequired = Boolean(field.required)
  const placeholder = field.placeholder ?? undefined

  switch (field.type) {
    case FormFieldTypeEnum.TEXT:
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
    case FormFieldTypeEnum.EMAIL:
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
    case FormFieldTypeEnum.MASKED_TEXT:
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
    case FormFieldTypeEnum.TEXTAREA:
      return (
        <SynTextAreaField<FormSubmissionInput>
          name={field.value_name}
          label={field.label}
          fieldId={fieldId}
          isRequired={isRequired}
          hint={hint}
          placeholder={placeholder}
          isDisabled={isDisabled}
        />
      )
    case FormFieldTypeEnum.NUMBER:
      return (
        <SynDynamicFormNumberField
          field={field}
          fieldId={fieldId}
          hint={hint}
          isRequired={isRequired}
          isDisabled={isDisabled}
        />
      )
    case FormFieldTypeEnum.CHECKBOX:
      return (
        <SynDynamicFormCheckboxField
          field={field}
          fieldId={fieldId}
          hint={hint}
          isRequired={isRequired}
          isDisabled={isDisabled}
        />
      )
    case FormFieldTypeEnum.DATE:
      return (
        <SynDynamicFormDateField
          field={field}
          fieldId={fieldId}
          hint={hint}
          isRequired={isRequired}
          isDisabled={isDisabled}
        />
      )
    case FormFieldTypeEnum.DROPDOWN:
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
    case FormFieldTypeEnum.MULTI_SELECT:
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
      const exhaustive: never = field
      return exhaustive
    }
  }
}
