import { Checkbox, DatePicker, FormGroup, NumberInput, Stack, StackItem, TextInput } from '@patternfly/react-core'
import type { FormField } from '@syntara/contracts'
import { useController } from 'react-hook-form'

import type { DateSubmissionValue, FormSubmissionInput } from '../../../forms'
import { formatDateYMD, parseDateYMD } from '../../../utils/dateUtils'
import { FormFieldError } from '../../FormFieldError'
import type { DynamicOptionsResolver } from '../SynDynamicForm.types'
import { SynFormField } from '../SynFormField'

import type { OptionsFormField } from './synDynamicFormFieldTypes'
import { SynDynamicFormOptionsSelect } from './SynDynamicFormOptionsSelect'

const DATE_COMPONENT_NAMES = ['date', 'time', 'timezone'] as const

type DateComponentName = (typeof DATE_COMPONENT_NAMES)[number]

function includedDateComponents(field: Extract<FormField, { type: 'date' }>): Array<DateComponentName> {
  const included: Record<DateComponentName, boolean> = {
    date: field.include_date ?? true,
    time: field.include_time ?? false,
    timezone: field.include_timezone ?? false,
  }
  return DATE_COMPONENT_NAMES.filter((name) => included[name])
}

function dateComponentValue(raw: unknown, name: DateComponentName): string {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    return ''
  }
  const value: unknown = Reflect.get(raw, name)
  return typeof value === 'string' ? value : ''
}

function updateDateValue(
  raw: unknown,
  updatedComponent: DateComponentName,
  updatedValue: string,
  included: Array<DateComponentName>
): DateSubmissionValue | '' {
  const value: DateSubmissionValue = {}
  for (const name of included) {
    value[name] = name === updatedComponent ? updatedValue : dateComponentValue(raw, name)
  }
  return included.every((name) => value[name] === '') ? '' : value
}

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
  const primaryComponent = included[0]
  const componentId = (name: DateComponentName) => (name === primaryComponent ? fieldId : `${fieldId}-${name}`)

  return (
    <SynFormField<FormSubmissionInput>
      name={field.value_name}
      label={field.label}
      fieldId={`${fieldId}-group`}
      isRequired={isRequired}
      hideFormGroupLabel
      hint={hint}
    >
      {({ field: rhfField, fieldState }) => (
        <Stack hasGutter>
          {included.map((name) => (
            <StackItem key={name}>
              <FormGroup
                label={`${field.label} ${name === 'timezone' ? 'time zone' : name}`}
                fieldId={componentId(name)}
                isRequired={isRequired}
              >
                {name === 'date' ? (
                  <DatePicker
                    value={dateComponentValue(rhfField.value, name)}
                    onChange={(_event, value) =>
                      rhfField.onChange(updateDateValue(rhfField.value, name, value, included))
                    }
                    dateFormat={formatDateYMD}
                    dateParse={parseDateYMD}
                    isDisabled={isDisabled}
                    inputProps={{
                      id: componentId(name),
                      validated: fieldState.error ? 'error' : 'default',
                      onBlur: rhfField.onBlur,
                    }}
                    appendTo={() => document.body}
                  />
                ) : (
                  <TextInput
                    id={componentId(name)}
                    type={name === 'time' ? 'time' : 'text'}
                    placeholder={name === 'timezone' ? 'America/New_York' : undefined}
                    value={dateComponentValue(rhfField.value, name)}
                    onChange={(_event, value) =>
                      rhfField.onChange(updateDateValue(rhfField.value, name, value, included))
                    }
                    onBlur={rhfField.onBlur}
                    isDisabled={isDisabled}
                    validated={fieldState.error ? 'error' : 'default'}
                  />
                )}
              </FormGroup>
            </StackItem>
          ))}
        </Stack>
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
