import type { SynDynamicFormSelectOption } from '../SynDynamicForm.types'

import type { DynamicOptionsSource } from './synDynamicFormFieldTypes'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isOptionScalar(value: unknown): value is string | number | boolean {
  const kind = typeof value
  return kind === 'string' || kind === 'number' || kind === 'boolean'
}

/**
 * Maps upstream expression output (array of objects) to select options using
 * {@link DynamicOptionsSource.label_key} and {@link DynamicOptionsSource.value_key}
 * (both required by the authored form definition).
 */
export function mapDynamicOptionsFromRecords(
  records: readonly unknown[],
  config: DynamicOptionsSource
): SynDynamicFormSelectOption[] {
  const labelKey = config.label_key
  const valueKey = config.value_key

  return records.map((record, index) => {
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
  result: readonly unknown[],
  config: DynamicOptionsSource
): SynDynamicFormSelectOption[] {
  return mapDynamicOptionsFromRecords(result, config)
}
