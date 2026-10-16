import { Checkbox, NumberInput } from '@patternfly/react-core'
import type { FormField } from '@syntara/contracts'
import { useController } from 'react-hook-form'

import type { DateSubmissionValue, FormSubmissionInput } from '../../../forms'
import { includedDateComponents, type DateValueShape } from '../../../forms/dateFieldUtils'
import { FormFieldError } from '../../FormFieldError'
import { FormDateValueInputs } from '../FormDateValueInputs'
import type { DynamicOptionsResolver } from '../SynDynamicForm.types'
import { SynFormField } from '../SynFormField'

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

/**
 * Maps the stored form value to a `NumberInput` value.
 *
 * Returns `''` (not `undefined`) for an empty field: `NumberInput` defaults an
 * `undefined` value to `0`, which would make a cleared field snap back to zero
 * and would also overwrite a partially typed entry such as a lone `-`.
 */
function parseNumberFieldValue(value: unknown): number | '' {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value !== '') {
    const parsed = Number.parseFloat(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return ''
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
            // NumberInput spreads unknown props onto its wrapper div, so the id
            // and accessible name have to be routed to the inner text input for
            // the FormGroup label to point at it.
            inputProps={{ id: fieldId }}
            inputName={rhfField.name}
            inputAriaLabel={field.label}
            value={displayValue}
            isDisabled={isDisabled}
            validated={fieldState.error ? 'error' : 'default'}
            onMinus={() => {
              const base = displayValue === '' ? 0 : displayValue
              rhfField.onChange(base - 1)
            }}
            onPlus={() => {
              const base = displayValue === '' ? 0 : displayValue
              rhfField.onChange(base + 1)
            }}
            onBlur={rhfField.onBlur}
            onChange={(event) => {
              const target = event.target as HTMLInputElement
              // On blur NumberInput rewrites the input to `Number(value)` and
              // reports it through onChange, turning an empty field into 0.
              // Undo that write so an intentionally empty field stays empty;
              // the form value is already '' so React will not re-render here.
              if (event.type === 'blur' && displayValue === '') {
                target.value = ''
                return
              }
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
          allowEmptyTimezone
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
