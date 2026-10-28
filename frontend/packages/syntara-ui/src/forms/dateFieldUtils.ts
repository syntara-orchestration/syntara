import type { FormDefinition, FormField } from '@syntara/contracts'

import { dateDefaultSuppliesExtraComponentsMessage } from './dateFieldValidationMessages'
import type { FormDefinitionSchemaInput } from './formDefinitionSchema'

export const DATE_COMPONENT_NAMES = ['date', 'time', 'timezone'] as const

export type DateComponentName = (typeof DATE_COMPONENT_NAMES)[number]

export type DateFormField = Extract<FormField, { type: 'date' }>

export type DateValueShape = {
  date?: string | null
  time?: string | null
  timezone?: string | null
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function coerceDateValueShape(value: unknown): DateValueShape | null {
  if (!isObjectRecord(value)) {
    return null
  }
  const shape: DateValueShape = {}
  for (const key of DATE_COMPONENT_NAMES) {
    if (!(key in value)) {
      continue
    }
    const part = value[key]
    if (part === null || typeof part === 'string') {
      shape[key] = part
    }
  }
  return shape
}

/** Component names that carry a non-empty value, in canonical order. */
function suppliedDateComponents(value: DateValueShape): DateComponentName[] {
  return DATE_COMPONENT_NAMES.filter((name) => {
    const part = value[name]
    return part != null && part !== ''
  })
}

/** True when the default supplies every component this field collects (substitutable on submit). */
export function dateDefaultCoversAllIncludedComponents(field: DateFormField): boolean {
  const shape = coerceDateValueShape(field.default)
  if (shape === null) {
    return false
  }
  const included = includedDateComponents(field)
  const supplied = new Set(suppliedDateComponents(shape))
  return included.every((name) => supplied.has(name))
}

/** Components this date field collects, in canonical order. */
export function includedDateComponents(field: DateFormField): DateComponentName[] {
  const included: Record<DateComponentName, boolean> = {
    date: field.include_date ?? true,
    time: field.include_time ?? false,
    timezone: field.include_timezone ?? false,
  }
  return DATE_COMPONENT_NAMES.filter((name) => included[name])
}

/** Drop default parts that are no longer collected. Returns null when nothing remains. */
function pruneDateValueForIncludes(
  value: DateValueShape | null | undefined,
  includes: Record<DateComponentName, boolean>
): DateValueShape | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const next: DateValueShape = {}
  for (const name of DATE_COMPONENT_NAMES) {
    if (!includes[name]) {
      continue
    }
    const part = value[name]
    if (part != null && part !== '') {
      next[name] = part
    }
  }

  if (next.date == null && next.time == null && next.timezone == null) {
    return null
  }
  return next
}

export function isDateFieldDateAndTimezoneWithoutTime(field: FormField): boolean {
  if (field.type !== 'date') {
    return false
  }
  const includes = dateIncludesFromField(field)
  return includes.date && includes.timezone && !includes.time
}

export function dateIncludesFromField(field: FormField): Record<DateComponentName, boolean> {
  if (field.type !== 'date') {
    return { date: true, time: false, timezone: false }
  }
  return {
    date: field.include_date ?? true,
    time: field.include_time ?? false,
    timezone: field.include_timezone ?? false,
  }
}

function countIncludedDateComponents(includes: Record<DateComponentName, boolean>): number {
  return DATE_COMPONENT_NAMES.filter((name) => includes[name]).length
}

/** True when this component is checked and it is the only one still included. */
export function isSoleIncludedDateComponent(
  includes: Record<DateComponentName, boolean>,
  name: DateComponentName
): boolean {
  return includes[name] && countIncludedDateComponents(includes) === 1
}

/**
 * Prune default parts that the field no longer collects.
 * Partial defaults (some included components blank) are preserved.
 */
export function normalizeDateDefaultForIncludes(
  value: DateValueShape | null | undefined,
  includes: Record<DateComponentName, boolean>
): DateValueShape | null {
  return pruneDateValueForIncludes(value, includes)
}

/** Initial answer for SynDynamicForm / form trigger run (partial defaults are prefilled for editing). */
export function buildDateFieldFormDefault(field: DateFormField): DateValueShape | '' {
  if (field.default == null) {
    return ''
  }
  const normalized = normalizeDateDefaultForIncludes(coerceDateValueShape(field.default), dateIncludesFromField(field))
  return normalized ?? ''
}

/**
 * Returns an error message when the default supplies components the field does not collect.
 * Missing components are not flagged — partial defaults are allowed.
 */
export function getDateDefaultCompletenessError(value: unknown, included: DateComponentName[]): string | undefined {
  if (value == null) {
    return undefined
  }

  const defaultValue = coerceDateValueShape(value)
  if (defaultValue === null) {
    return undefined
  }

  const extra = DATE_COMPONENT_NAMES.filter(
    (component) => !included.includes(component) && defaultValue[component] != null
  )
  return extra.length > 0 ? dateDefaultSuppliesExtraComponentsMessage(extra) : undefined
}

/** Apply a single show-in-form toggle; returns null when all components would be off. */
export function nextDateIncludes(
  current: Record<DateComponentName, boolean>,
  name: DateComponentName,
  checked: boolean
): Record<DateComponentName, boolean> | null {
  const next = { ...current, [name]: checked }

  if (!next.date && !next.time && !next.timezone) {
    return null
  }

  return next
}

/** Normalize a single date field so it passes backend FormDefinition validation. */
export function sanitizeDateFieldForApi(field: FormField): FormField {
  if (field.type !== 'date') {
    return field
  }

  let includes = dateIncludesFromField(field)
  if (!includes.date && !includes.time && !includes.timezone) {
    includes = { ...includes, date: true }
  }

  const defaultValue = coerceDateValueShape(field.default)
  const normalizedDefault = normalizeDateDefaultForIncludes(defaultValue, includes)

  return {
    ...field,
    include_date: includes.date,
    include_time: includes.time,
    include_timezone: includes.timezone,
    default: normalizedDefault,
  }
}

/** Apply date-field API rules before parsing or persisting a form definition. */
export function prepareFormDefinitionForCommit(
  definition: FormDefinitionSchemaInput | FormDefinition
): FormDefinitionSchemaInput {
  return {
    fields: definition.fields.map((field) => sanitizeDateFieldForApi(field)),
  }
}
