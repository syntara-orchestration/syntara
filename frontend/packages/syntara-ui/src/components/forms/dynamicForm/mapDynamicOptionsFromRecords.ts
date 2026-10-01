import type { SynDynamicFormSelectOption } from '../SynDynamicForm.types'

import type { DynamicOptionsSource } from './synDynamicFormFieldTypes'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isOptionScalar(value: unknown): value is string | number | boolean {
  const kind = typeof value
  return kind === 'string' || kind === 'number' || kind === 'boolean'
}

export function isSynDynamicFormSelectOption(value: unknown): value is SynDynamicFormSelectOption {
  return isRecord(value) && typeof value.label === 'string' && isOptionScalar(value.value)
}

/**
 * Maps upstream expression output (array of objects) to select options using
 * {@link DynamicOptionsSource.label_key} and {@link DynamicOptionsSource.value_key}
 * (defaults: `display_label` / `value`, matching static options).
 */
export function mapDynamicOptionsFromRecords(
  records: readonly unknown[],
  config: DynamicOptionsSource
): SynDynamicFormSelectOption[] {
  const labelKey = config.label_key ?? 'display_label'
  const valueKey = config.value_key ?? 'value'

  return records.map((record, index) => {
    if (isSynDynamicFormSelectOption(record)) {
      return record
    }
    if (!isRecord(record)) {
      throw new TypeError(`Dynamic option at index ${index} must be an object`)
    }
    const label = record[labelKey]
    const value = record[valueKey]
    if (typeof label !== 'string' || label.length === 0) {
      throw new TypeError(`Dynamic option at index ${index} is missing a string label at key "${labelKey}"`)
    }
    if (!isOptionScalar(value)) {
      throw new TypeError(`Dynamic option at index ${index} is missing a scalar value at key "${valueKey}"`)
    }
    return { label, value }
  })
}

export function normalizeDynamicOptionsResult(
  result: readonly SynDynamicFormSelectOption[] | readonly unknown[],
  config: DynamicOptionsSource
): SynDynamicFormSelectOption[] {
  if (result.length === 0) {
    return []
  }
  const prebuilt: SynDynamicFormSelectOption[] = []
  for (const item of result) {
    if (isSynDynamicFormSelectOption(item)) {
      prebuilt.push(item)
    }
  }
  if (prebuilt.length === result.length) {
    return prebuilt
  }
  return mapDynamicOptionsFromRecords(result, config)
}
