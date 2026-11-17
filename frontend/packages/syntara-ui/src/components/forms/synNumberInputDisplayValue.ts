/**
 * Maps a stored form value to a `NumberInput` display value.
 *
 * Returns `''` (not `undefined`) for an empty field: `NumberInput` defaults an
 * `undefined` value to `0`, which would make a cleared field snap back to zero
 * and would also overwrite a partially typed entry such as a lone `-`.
 */
export function parseSynNumberInputDisplayValue(value: unknown): number | '' {
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
