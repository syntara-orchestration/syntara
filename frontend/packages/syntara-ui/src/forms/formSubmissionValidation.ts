import type { FormDefinition, FormField } from '@syntara/contracts'

import { FormFieldTypeEnum } from './formFieldTypeEnum'
import type { FormSubmissionData, FormSubmissionInput } from './formTypes'
import {
  FormDataValidationError,
  FormDefinitionValidationError,
  type FormFieldValidationError,
} from './formValidationErrors'

const MISSING = Symbol('missing')

type OptionScalar = string | number | boolean

type Coercer = (raw: unknown) => OptionScalar | Array<OptionScalar>

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

function coerceDate(raw: unknown): string {
  if (typeof raw !== 'string') {
    throw new TypeError(`Must be a date string, got ${typeof raw}`)
  }
  if (raw.length !== 10 || raw[4] !== '-' || raw[7] !== '-') {
    throw new Error('Must be a valid ISO 8601 date (YYYY-MM-DD)')
  }
  const year = Number(raw.slice(0, 4))
  const month = Number(raw.slice(5, 7))
  const day = Number(raw.slice(8, 10))
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    throw new TypeError('Must be a valid ISO 8601 date (YYYY-MM-DD)')
  }
  const date = new Date(Date.UTC(year, month - 1, day))
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    throw new Error('Must be a valid ISO 8601 date (YYYY-MM-DD)')
  }
  return raw
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

const COERCERS: Record<FormField['type'], Coercer> = {
  [FormFieldTypeEnum.TEXT]: coerceString,
  [FormFieldTypeEnum.TEXTAREA]: coerceString,
  [FormFieldTypeEnum.MASKED_TEXT]: coerceString,
  [FormFieldTypeEnum.EMAIL]: coerceEmail,
  [FormFieldTypeEnum.NUMBER]: coerceNumber,
  [FormFieldTypeEnum.CHECKBOX]: coerceCheckbox,
  [FormFieldTypeEnum.DATE]: coerceDate,
  [FormFieldTypeEnum.DROPDOWN]: coerceDropdown,
  [FormFieldTypeEnum.MULTI_SELECT]: coerceMultiSelect,
}

function coerceField(field: FormField, raw: unknown): OptionScalar | Array<OptionScalar> {
  return COERCERS[field.type](raw)
}

type SelectFormField = Extract<FormField, { type: 'dropdown' }> | Extract<FormField, { type: 'multi_select' }>

type SelectFormFieldWithStaticOptions = SelectFormField & {
  options: Extract<SelectFormField['options'], { source: 'static' }>
}

function isStaticOptions(field: FormField): field is SelectFormFieldWithStaticOptions {
  if (field.type !== FormFieldTypeEnum.DROPDOWN && field.type !== FormFieldTypeEnum.MULTI_SELECT) {
    return false
  }
  return field.options.source === 'static'
}

function checkStaticOptionMembership(
  field: SelectFormFieldWithStaticOptions,
  coerced: FormSubmissionData[string]
): FormFieldValidationError | null {
  const validValues = new Set(field.options.values.map((option) => option.value))

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

  if (Array.isArray(coerced) || !validValues.has(coerced)) {
    if (Array.isArray(coerced)) {
      return fieldError(field, 'type', 'Dropdown expects a single value, not a list')
    }
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
    const isFormatError =
      field.type === FormFieldTypeEnum.EMAIL && error instanceof Error && !(error instanceof TypeError)
    return {
      status: 'invalid',
      error: fieldError(field, isFormatError ? 'invalid_format' : 'type', message),
    }
  }

  if (field.type === FormFieldTypeEnum.CHECKBOX && field.required && coerced === false) {
    return { status: 'invalid', error: fieldError(field, 'must_be_checked', 'This checkbox must be checked') }
  }

  const optionError = isStaticOptions(field) ? checkStaticOptionMembership(field, coerced) : null
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
          ? `Default value is not valid for a '${field.type}' field: ${error.message}`
          : `Default value is not valid for a '${field.type}' field`
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
