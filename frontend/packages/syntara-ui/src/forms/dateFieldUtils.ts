import type { FormDefinition, FormField } from '@syntara/contracts'

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

export function isDateFieldTimeWithoutTimezone(field: FormField): boolean {
  if (field.type !== 'date') {
    return false
  }
  const includes = dateIncludesFromField(field)
  return includes.time && !includes.timezone
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
 * Prune default parts and clear the default when it no longer supplies every included component.
 * Keeps form-definition validation passing after toggling show-in-form checkboxes.
 */
export function normalizeDateDefaultForIncludes(
  value: DateValueShape | null | undefined,
  includes: Record<DateComponentName, boolean>
): DateValueShape | null {
  const pruned = pruneDateValueForIncludes(value, includes)
  if (!pruned) {
    return null
  }

  for (const name of DATE_COMPONENT_NAMES) {
    if (!includes[name]) {
      continue
    }
    const part = pruned[name]
    if (part == null || part === '') {
      return null
    }
  }
  return pruned
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
  if (includes.time && !includes.timezone) {
    includes = { ...includes, timezone: true }
  }
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
