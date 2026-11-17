import { Checkbox } from '@patternfly/react-core'
import type { FormField } from '@syntara/contracts'
import { useController } from 'react-hook-form'

import type { DateSubmissionValue, FormSubmissionInput } from '../../../forms'
import { includedDateComponents, type DateValueShape } from '../../../forms/dateFieldUtils'
import { FormFieldError } from '../../FormFieldError'
import { FormDateValueInputs } from '../FormDateValueInputs'
import type { DynamicOptionsResolver } from '../SynDynamicForm.types'
import { SynFormField } from '../SynFormField'
import { SynNumberInputControl } from '../SynNumberInputControl'

import type { OptionsFormField } from './synDynamicFormFieldTypes'
import { SynDynamicFormOptionsSelect } from './SynDynamicFormOptionsSelect'

function toSubmissionDateValue(next: DateValueShape | null): DateSubmissionValue | '' {
  if (!next) {
    return ''
  }
  const value: DateSubmissionValue = {}
  if (next.date) {
    value.date = next.date
  }
  if (next.time) {
    value.time = next.time
  }
  if (next.timezone) {
    value.timezone = next.timezone
  }
  return Object.keys(value).length === 0 ? '' : value
}

export function SynDynamicFormNumberField({
  field,
  fieldId,
  hint,
  isRequired,
  isDisabled,
}: Readonly<{
  field: Extract<FormField, { type: 'number' }>
  fieldId: string
  hint?: string
  isRequired: boolean
  isDisabled?: boolean
}>) {
  return (
    <SynFormField<FormSubmissionInput>
      name={field.value_name}
      label={field.label}
      fieldId={fieldId}
      isRequired={isRequired}
      hint={hint}
    >
      {({ field: rhfField, fieldState }) => (
        <SynNumberInputControl
          fieldId={fieldId}
          inputName={rhfField.name}
          ariaLabel={field.label}
          value={rhfField.value}
          emptyValue=""
          onChange={rhfField.onChange}
          onBlur={rhfField.onBlur}
          isDisabled={isDisabled}
          validated={fieldState.error ? 'error' : 'default'}
        />
      )}
    </SynFormField>
  )
}

export function SynDynamicFormCheckboxField({
  field,
  fieldId,
  hint,
  isRequired,
  isDisabled,
}: Readonly<{
  field: Extract<FormField, { type: 'checkbox' }>
  fieldId: string
  hint?: string
  isRequired: boolean
  isDisabled?: boolean
}>) {
  const { field: rhfField, fieldState } = useController<FormSubmissionInput>({ name: field.value_name })

  return (
    <>
      <Checkbox
        id={fieldId}
        name={rhfField.name}
        label={field.label}
        isRequired={isRequired}
        description={fieldState.error ? undefined : hint}
        isChecked={Boolean(rhfField.value)}
        isDisabled={isDisabled}
        isValid={fieldState.error ? false : undefined}
        onChange={(_event, checked) => rhfField.onChange(checked)}
        onBlur={rhfField.onBlur}
      />
      {fieldState.error ? <FormFieldError error={fieldState.error} /> : null}
    </>
  )
}

export function SynDynamicFormDateField({
  field,
  fieldId,
  hint,
  isRequired,
  isDisabled,
}: Readonly<{
  field: Extract<FormField, { type: 'date' }>
  fieldId: string
  hint?: string
  isRequired: boolean
  isDisabled?: boolean
}>) {
  const included = includedDateComponents(field)

  return (
    <SynFormField<FormSubmissionInput>
      name={field.value_name}
      label={field.label}
      fieldId={fieldId}
      isRequired={isRequired}
      hint={hint}
    >
      {({ field: rhfField, fieldState }) => (
        <FormDateValueInputs
          included={included}
          value={rhfField.value && typeof rhfField.value === 'object' ? rhfField.value : null}
          onChange={(next) => rhfField.onChange(toSubmissionDateValue(next))}
          onBlur={rhfField.onBlur}
          idPrefix={fieldId}
          isDisabled={isDisabled}
          validated={fieldState.error ? 'error' : 'default'}
          dateAriaLabel={`${field.label} date`}
          timeAriaLabel={`${field.label} time`}
          timezoneAriaLabel={`${field.label} time zone`}
        />
      )}
    </SynFormField>
  )
}

export function SynDynamicFormOptionsField({
  field,
  fieldId,
  hint,
  isRequired,
  isMulti,
  isDisabled,
  resolveDynamicOptions,
}: Readonly<{
  field: OptionsFormField
  fieldId: string
  hint?: string
  isRequired: boolean
  isMulti: boolean
  isDisabled?: boolean
  resolveDynamicOptions?: DynamicOptionsResolver
}>) {
  return (
    <SynFormField<FormSubmissionInput>
      name={field.value_name}
      label={field.label}
      fieldId={fieldId}
      isRequired={isRequired}
      hint={hint}
    >
      {({ field: rhfField }) => (
        <SynDynamicFormOptionsSelect
          field={field}
          rhfField={rhfField}
          fieldId={fieldId}
          ariaLabel={field.label}
          isMulti={isMulti}
          isDisabled={isDisabled}
          resolveDynamicOptions={resolveDynamicOptions}
        />
      )}
    </SynFormField>
  )
}
