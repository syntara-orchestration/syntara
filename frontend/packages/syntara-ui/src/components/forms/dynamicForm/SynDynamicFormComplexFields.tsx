import { Checkbox, DatePicker, NumberInput } from '@patternfly/react-core'
import type { FormField } from '@syntara/contracts'

import type { FormSubmissionInput } from '../../../forms'
import { formatDateYMD, parseDateYMD } from '../../../utils/dateUtils'
import type { DynamicOptionsResolver } from '../SynDynamicForm.types'
import { SynFormField } from '../SynFormField'

import type { OptionsFormField } from './synDynamicFormFieldTypes'
import { SynDynamicFormOptionsSelect } from './SynDynamicFormOptionsSelect'

function parseNumberFieldValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value !== '') {
    const parsed = Number.parseFloat(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return undefined
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
      {({ field: rhfField, fieldState }) => {
        const displayValue = parseNumberFieldValue(rhfField.value)

        return (
          <NumberInput
            id={fieldId}
            aria-label={field.label}
            value={displayValue}
            isDisabled={isDisabled}
            validated={fieldState.error ? 'error' : 'default'}
            onMinus={() => {
              const base = displayValue ?? 0
              rhfField.onChange(base - 1)
            }}
            onPlus={() => {
              const base = displayValue ?? 0
              rhfField.onChange(base + 1)
            }}
            onBlur={rhfField.onBlur}
            onChange={(event) => {
              const target = event.target as HTMLInputElement
              if (target.value === '') {
                rhfField.onChange('')
                return
              }
              const parsed = Number.parseFloat(target.value)
              if (!Number.isNaN(parsed)) {
                rhfField.onChange(parsed)
              }
            }}
          />
        )
      }}
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
  return (
    <SynFormField<FormSubmissionInput>
      name={field.value_name}
      label={field.label}
      fieldId={fieldId}
      isRequired={isRequired}
      hint={hint}
    >
      {({ field: rhfField, fieldState }) => (
        <Checkbox
          id={fieldId}
          aria-label={field.label}
          isChecked={Boolean(rhfField.value)}
          isDisabled={isDisabled}
          onChange={(_event, checked) => rhfField.onChange(checked)}
          onBlur={rhfField.onBlur}
          aria-invalid={fieldState.error ? true : undefined}
        />
      )}
    </SynFormField>
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
  return (
    <SynFormField<FormSubmissionInput>
      name={field.value_name}
      label={field.label}
      fieldId={fieldId}
      isRequired={isRequired}
      hint={hint}
    >
      {({ field: rhfField, fieldState }) => (
        <DatePicker
          value={typeof rhfField.value === 'string' ? rhfField.value : ''}
          onChange={(_event, value) => rhfField.onChange(value)}
          dateFormat={formatDateYMD}
          dateParse={parseDateYMD}
          isDisabled={isDisabled}
          aria-label={field.label}
          inputProps={{
            id: fieldId,
            validated: fieldState.error ? 'error' : 'default',
            onBlur: rhfField.onBlur,
          }}
          appendTo={() => document.body}
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
