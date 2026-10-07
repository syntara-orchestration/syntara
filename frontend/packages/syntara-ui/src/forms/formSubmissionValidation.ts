import type { FormDefinition, FormField } from '@syntara/contracts'

import { FormFieldTypeEnum } from './formFieldTypeEnum'
import type { DateSubmissionValue, FormSubmissionData, FormSubmissionInput } from './formTypes'
import {
  FormDataValidationError,
  FormDefinitionValidationError,
  type FormFieldValidationError,
} from './formValidationErrors'

const MISSING = Symbol('missing')

type OptionScalar = string | number | boolean

type CoercedValue = FormSubmissionData[string]

function isEmptyValue(value: unknown): boolean {
  return value === '' || value === null || value === undefined || (Array.isArray(value) && value.length === 0)
}

function coerceString(raw: unknown): string {
  if (typeof raw !== 'string') {
    throw new TypeError(`Must be a string, got ${typeof raw}`)
  }
  return raw
}

function emailSegmentIsValid(segment: string): boolean {
  if (segment.length === 0) {
    return false
  }
  for (const char of segment) {
    if (char === '@') {
      return false
    }
    const code = char.codePointAt(0)
    if (code === undefined || code <= 32 || code === 127) {
      return false
    }
  }
  return true
}

function isValidEmailDomain(domain: string): boolean {
  return domain.includes('.') && !domain.startsWith('.') && !domain.endsWith('.')
}

function isValidEmailShape(local: string, domain: string): boolean {
  if (!emailSegmentIsValid(local) || !emailSegmentIsValid(domain)) {
    return false
  }
  return isValidEmailDomain(domain)
}

function splitEmailAtLastAt(value: string): { local: string; domain: string } | null {
  for (let index = value.length - 1; index >= 0; index -= 1) {
    if (value.codePointAt(index) === 64) {
      if (index <= 0 || index === value.length - 1) {
        return null
      }
      return {
        local: value.slice(0, index),
        domain: value.slice(index + 1).toLowerCase(),
      }
    }
  }
  return null
}

function coerceEmail(raw: unknown): string {
  const value = coerceString(raw)
  const parts = splitEmailAtLastAt(value)
  if (parts === null || !isValidEmailShape(parts.local, parts.domain)) {
    throw new Error('Must be a valid email address')
  }
  return `${parts.local}@${parts.domain}`
}

function coerceNumber(raw: unknown): number {
  if (typeof raw === 'boolean') {
    throw new TypeError('Boolean values are not accepted as numbers')
  }
  if (typeof raw === 'number') {
    if (!Number.isFinite(raw)) {
      throw new TypeError('Infinite and NaN values are not accepted')
    }
    return raw
  }
  if (typeof raw === 'string') {
    const parsed = Number(raw)
    if (!Number.isFinite(parsed)) {
      throw new TypeError('Must be a valid number string')
    }
    return parsed
  }
  throw new TypeError(`Must be a number, got ${typeof raw}`)
}

function coerceCheckbox(raw: unknown): boolean {
  if (typeof raw === 'boolean') {
    return raw
  }
  if (typeof raw === 'number' && (raw === 0 || raw === 1)) {
    return Boolean(raw)
  }
  if (typeof raw === 'string') {
    const lower = raw.toLowerCase()
    if (['true', 'on', 'yes', '1'].includes(lower)) {
      return true
    }
    if (['false', 'off', 'no', '0'].includes(lower)) {
      return false
    }
    throw new Error('Must be a boolean value (true/false, yes/no, on/off, 1/0)')
  }
  throw new TypeError(`Must be a boolean, got ${typeof raw}`)
}

const DATE_COMPONENT_NAMES = ['date', 'time', 'timezone'] as const

type DateComponentName = (typeof DATE_COMPONENT_NAMES)[number]

type DateFormField = Extract<FormField, { type: 'date' }>

/** The components a date field collects, in DATE_COMPONENT_NAMES order. */
function includedDateComponents(field: DateFormField): Array<DateComponentName> {
  const included: Record<DateComponentName, boolean> = {
    date: field.include_date ?? true,
    time: field.include_time ?? false,
    timezone: field.include_timezone ?? false,
  }
  return DATE_COMPONENT_NAMES.filter((name) => included[name])
}

function assertIsoDate(raw: string): void {
  if (raw.length !== 10 || raw[4] !== '-' || raw[7] !== '-') {
    throw new Error('date must be a date in YYYY-MM-DD format')
  }
  const year = Number(raw.slice(0, 4))
  const month = Number(raw.slice(5, 7))
  const day = Number(raw.slice(8, 10))
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    throw new Error('date must be a date in YYYY-MM-DD format')
  }
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) {
    throw new Error(`Invalid date: '${raw}'. Use a valid ISO 8601 date in YYYY-MM-DD format.`)
  }
}

function assertTime(raw: string): void {
  if (!/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(raw)) {
    throw new Error('time must be a 24-hour time in HH:MM format')
  }
}

function assertTimezone(raw: string): void {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: raw })
  } catch {
    throw new Error(`Invalid timezone: '${raw}'. Use a valid IANA timezone name, such as 'America/New_York'.`)
  }
}

const DATE_COMPONENT_ASSERTIONS: Record<DateComponentName, (raw: string) => void> = {
  date: assertIsoDate,
  time: assertTime,
  timezone: assertTimezone,
}

/**
 * Coerce to a date value object holding exactly the field's components.
 *
 * Mirrors the backend `_coerce_date`: the value is always an object, every
 * included component is mandatory, and components the field does not collect
 * are rejected rather than silently dropped.
 */
function toDateComponentEntries(raw: unknown, included: Array<DateComponentName>): Record<string, unknown> {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new TypeError(`Must be an object with keys: ${included.join(', ')}; got ${typeof raw}`)
  }

  const entries = raw as Record<string, unknown>
  for (const key of Object.keys(entries)) {
    if (!DATE_COMPONENT_NAMES.includes(key as DateComponentName)) {
      throw new Error(`'${key}' is not a date component`)
    }
  }
  return entries
}

function validateDateComponent(name: DateComponentName, supplied: unknown): string {
  if (typeof supplied !== 'string') {
    throw new TypeError(`${name} must be a string, got ${typeof supplied}`)
  }
  DATE_COMPONENT_ASSERTIONS[name](supplied)
  return supplied
}

function coerceDate(field: DateFormField, raw: unknown): DateSubmissionValue {
  const included = includedDateComponents(field)
  const entries = toDateComponentEntries(raw, included)

  const value: DateSubmissionValue = {}
  const missing: Array<DateComponentName> = []

  for (const name of DATE_COMPONENT_NAMES) {
    // Drop blanks so an untouched input posting "" reads as absent.
    const supplied = isEmptyValue(entries[name]) ? undefined : entries[name]

    if (!included.includes(name)) {
      if (supplied !== undefined) {
        throw new Error(`This field does not collect: ${name}`)
      }
    } else if (supplied === undefined) {
      missing.push(name)
    } else {
      value[name] = validateDateComponent(name, supplied)
    }
  }

  if (missing.length > 0) {
    throw new Error(`Missing required ${missing.length === 1 ? 'component' : 'components'}: ${missing.join(', ')}`)
  }

  return value
}

function isOptionScalarValue(raw: unknown): raw is OptionScalar {
  const kind = typeof raw
  return kind === 'string' || kind === 'number' || kind === 'boolean'
}

function coerceOptionScalar(raw: unknown): OptionScalar {
  const kind = typeof raw
  if (isOptionScalarValue(raw)) {
    return raw
  }
  throw new TypeError(`Must be a string, number, or boolean, got ${kind}`)
}

function coerceDropdown(raw: unknown): OptionScalar {
  if (Array.isArray(raw)) {
    throw new TypeError('Dropdown expects a single value, not a list')
  }
  if (typeof raw === 'object' && raw !== null) {
    throw new TypeError('Dropdown expects a scalar value, not a dict')
  }
  return coerceOptionScalar(raw)
}

function coerceMultiSelect(raw: unknown): Array<OptionScalar> {
  if (Array.isArray(raw)) {
    return raw.map((item) => coerceOptionScalar(item))
  }
  if (typeof raw === 'object' && raw !== null) {
    throw new TypeError('Multi-select expects a list or scalar, not a dict')
  }
  return [coerceOptionScalar(raw)]
}

/**
 * Coerce a submitted value according to its field's type.
 *
 * `FormField` is a closed union, so every field type needs a `case` here. The
 * `never` default makes a missing one a compile error.
 */
function coerceField(field: FormField, raw: unknown): CoercedValue {
  switch (field.type) {
    case FormFieldTypeEnum.TEXT:
    case FormFieldTypeEnum.TEXTAREA:
    case FormFieldTypeEnum.MASKED_TEXT:
      return coerceString(raw)
    case FormFieldTypeEnum.EMAIL:
      return coerceEmail(raw)
    case FormFieldTypeEnum.NUMBER:
      return coerceNumber(raw)
    case FormFieldTypeEnum.CHECKBOX:
      return coerceCheckbox(raw)
    case FormFieldTypeEnum.DATE:
      // The only coercer that reads its own definition, to learn which date
      // components the field collects.
      return coerceDate(field, raw)
    case FormFieldTypeEnum.DROPDOWN:
      return coerceDropdown(raw)
    case FormFieldTypeEnum.MULTI_SELECT:
      return coerceMultiSelect(raw)
    default: {
      const exhaustive: never = field
      return exhaustive
    }
  }
}

type SelectFormField = Extract<FormField, { type: 'dropdown' }> | Extract<FormField, { type: 'multi_select' }>

type SelectFormFieldWithOptionList = SelectFormField & {
  options: Extract<SelectFormField['options'], { source: 'static' | 'dynamic_resolved' }>
}

function hasOptionList(field: FormField): field is SelectFormFieldWithOptionList {
  if (field.type !== FormFieldTypeEnum.DROPDOWN && field.type !== FormFieldTypeEnum.MULTI_SELECT) {
    return false
  }
  return field.options.source === 'static' || field.options.source === 'dynamic_resolved'
}

function checkOptionMembership(
  field: SelectFormFieldWithOptionList,
  coerced: FormSubmissionData[string]
): FormFieldValidationError | null {
  const validValues = new Set<OptionScalar>(field.options.values.map((option) => option.value))

  if (field.type === FormFieldTypeEnum.MULTI_SELECT) {
    if (!Array.isArray(coerced)) {
      return fieldError(field, 'type', 'Must be a list')
    }
    let invalidCount = 0
    for (const value of coerced) {
      if (!validValues.has(value)) {
        invalidCount += 1
      }
    }
    if (invalidCount > 0) {
      return {
        field: field.value_name,
        label: field.label,
        code: 'not_in_options',
        message: `Invalid selection(s): ${invalidCount} value(s) not in option list`,
      }
    }
    return null
  }

  if (Array.isArray(coerced)) {
    return fieldError(field, 'type', 'Dropdown expects a single value, not a list')
  }
  if (!isOptionScalarValue(coerced)) {
    return fieldError(field, 'type', 'Dropdown expects a scalar value')
  }
  if (!validValues.has(coerced)) {
    return {
      field: field.value_name,
      label: field.label,
      code: 'not_in_options',
      message: 'Selected value is not in the option list',
    }
  }
  return null
}

function fieldError(
  field: FormField,
  code: FormFieldValidationError['code'],
  message: string
): FormFieldValidationError {
  return { field: field.value_name, label: field.label, code, message }
}

type FieldSubmissionOutcome =
  | { status: 'omit' }
  | { status: 'invalid'; error: FormFieldValidationError }
  | { status: 'valid'; value: FormSubmissionData[string] }

function resolveSubmittedRaw(field: FormField, submitted: FormSubmissionInput): unknown {
  let raw: unknown = Object.hasOwn(submitted, field.value_name) ? submitted[field.value_name] : MISSING

  if (field.type !== FormFieldTypeEnum.CHECKBOX && raw !== MISSING && isEmptyValue(raw)) {
    raw = MISSING
  }

  if (raw === MISSING && field.default != null) {
    raw = field.default
  }

  return raw
}

function validateFieldSubmission(field: FormField, submitted: FormSubmissionInput): FieldSubmissionOutcome {
  const raw = resolveSubmittedRaw(field, submitted)

  if (raw === MISSING) {
    if (field.required) {
      return { status: 'invalid', error: fieldError(field, 'required', 'This field is required') }
    }
    return { status: 'omit' }
  }

  let coerced: FormSubmissionData[string]
  try {
    coerced = coerceField(field, raw)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Invalid value'
    // Email and date coercers distinguish a wrong-typed value (TypeError) from
    // a right-typed value in the wrong format, matching the backend's codes.
    const distinguishesFormat = field.type === FormFieldTypeEnum.EMAIL || field.type === FormFieldTypeEnum.DATE
    const isFormatError = distinguishesFormat && error instanceof Error && !(error instanceof TypeError)
    return {
      status: 'invalid',
      error: fieldError(field, isFormatError ? 'invalid_format' : 'type', message),
    }
  }

  if (field.type === FormFieldTypeEnum.CHECKBOX && field.required && coerced === false) {
    return { status: 'invalid', error: fieldError(field, 'must_be_checked', 'This checkbox must be checked') }
  }

  const optionError = hasOptionList(field) ? checkOptionMembership(field, coerced) : null
  if (optionError) {
    return { status: 'invalid', error: optionError }
  }

  return { status: 'valid', value: coerced }
}

function unknownFieldErrors(form: FormDefinition, submitted: FormSubmissionInput): FormFieldValidationError[] {
  const knownNames = new Set(form.fields.map((f) => f.value_name))
  return Object.keys(submitted)
    .filter((key) => !knownNames.has(key))
    .map((key) => ({
      field: key,
      label: key,
      code: 'unknown_field' as const,
      message: 'Unknown field - not defined in form',
    }))
}

/**
 * Validate and coerce submitted form data against a parsed {@link FormDefinition}.
 * Mirrors backend `validate_form_submission` behavior for client-side checks.
 */
export function validateFormSubmission(form: FormDefinition, submitted: FormSubmissionInput): FormSubmissionData {
  const errors: FormFieldValidationError[] = []
  const cleaned: FormSubmissionData = {}

  for (const field of form.fields) {
    const outcome = validateFieldSubmission(field, submitted)
    if (outcome.status === 'invalid') {
      errors.push(outcome.error)
    } else if (outcome.status === 'valid') {
      cleaned[field.value_name] = outcome.value
    }
  }

  errors.push(...unknownFieldErrors(form, submitted))

  if (errors.length > 0) {
    throw new FormDataValidationError(errors)
  }

  return cleaned
}

/**
 * Validates that each field default can be coerced (builder / definition authoring).
 */
export function validateFormDefinitionDefaults(form: FormDefinition): void {
  const errors: FormFieldValidationError[] = []

  for (const field of form.fields) {
    if (field.type === FormFieldTypeEnum.CHECKBOX || field.default == null) {
      continue
    }
    try {
      coerceField(field, field.default)
    } catch (error) {
      const message =
        error instanceof Error
          ? `Initial answer is not valid for a '${field.type}' field: ${error.message}`
          : `Initial answer is not valid for a '${field.type}' field`
      errors.push(fieldError(field, 'invalid_default', message))
    }
  }

  if (errors.length > 0) {
    throw new FormDefinitionValidationError(errors)
  }
}

/** Validates defaults after structural parse. */
export function assertValidFormDefinition(form: FormDefinition): FormDefinition {
  validateFormDefinitionDefaults(form)
  return form
}
