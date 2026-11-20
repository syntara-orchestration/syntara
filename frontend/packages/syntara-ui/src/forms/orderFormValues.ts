import type { FormDefinition } from '@syntara/contracts'

/** Ordered `value_name`s from a form definition. */
export function formFieldValueNames(definition: FormDefinition): string[] {
  return definition.fields.map((field) => field.value_name)
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }

  const prototype: unknown = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

/**
 * Reorder a record to match the configured field order. Keys not listed in `order`
 * keep their existing relative order and follow the configured keys.
 */
export function orderValuesByFieldOrder<T>(values: T, order: readonly string[]): T {
  if (!isPlainObject(values)) {
    return values
  }

  const record = values
  const existingKeys = Object.keys(record)
  if (existingKeys.length === 0 || order.length === 0) {
    return values
  }

  const existingKeySet = new Set(existingKeys)
  const orderedKeys: string[] = []
  const orderedKeySet = new Set<string>()

  for (const key of order) {
    if (existingKeySet.has(key) && !orderedKeySet.has(key)) {
      orderedKeys.push(key)
      orderedKeySet.add(key)
    }
  }

  for (const key of existingKeys) {
    if (!orderedKeySet.has(key)) {
      orderedKeys.push(key)
    }
  }

  if (existingKeys.every((key, index) => key === orderedKeys[index])) {
    return values
  }

  return Object.fromEntries(orderedKeys.map((key): [string, unknown] => [key, record[key]])) as T
}
