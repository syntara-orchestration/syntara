import { FORM_FIELD_VALUE_NAME_MAX_LENGTH, isValidFormFieldValueName } from './formConstants'

function appendChar(
  result: string,
  char: string,
  previousWasSeparator: boolean
): { result: string; previousWasSeparator: boolean } {
  if (char === '_') {
    if (result.length > 0 && !previousWasSeparator) {
      return { result: `${result}_`, previousWasSeparator: true }
    }
    return { result, previousWasSeparator: true }
  }
  return { result: `${result}${char}`, previousWasSeparator: false }
}

function isAsciiLetterOrDigit(code: number): boolean {
  return (code >= 48 && code <= 57) || (code >= 97 && code <= 122)
}

/**
 * Converts a human-readable label into a `value_name`-safe identifier (snake_case).
 */
export function slugifyLabelToValueNameBase(label: string): string {
  const trimmed = label.trim().toLowerCase()
  if (trimmed.length === 0) {
    return 'field'
  }

  let result = ''
  let previousWasSeparator = false

  for (const char of trimmed) {
    const code = char.codePointAt(0)
    if (code === undefined) {
      continue
    }
    if (code === 95 || isAsciiLetterOrDigit(code)) {
      const next = appendChar(result, char, previousWasSeparator)
      result = next.result
      previousWasSeparator = next.previousWasSeparator
      continue
    }
    if (result.length > 0 && !previousWasSeparator) {
      result += '_'
      previousWasSeparator = true
    }
  }

  while (result.endsWith('_')) {
    result = result.slice(0, -1)
  }

  if (result.length === 0) {
    return 'field'
  }

  const first = result.codePointAt(0)
  if (first !== undefined && first >= 48 && first <= 57) {
    result = `field_${result}`
  }

  return result.slice(0, FORM_FIELD_VALUE_NAME_MAX_LENGTH)
}

/**
 * Generates a unique `value_name` from a label, avoiding collisions with `takenNames`.
 */
export function labelToValueName(label: string, takenNames: ReadonlyArray<string>): string {
  const taken = new Set(takenNames)
  const base = slugifyLabelToValueNameBase(label)
  const candidate = isValidFormFieldValueName(base) ? base : 'field'

  if (!taken.has(candidate)) {
    return candidate
  }

  for (let suffix = 2; suffix < 10_000; suffix += 1) {
    const withSuffix = `${candidate}_${suffix}`.slice(0, FORM_FIELD_VALUE_NAME_MAX_LENGTH)
    if (isValidFormFieldValueName(withSuffix) && !taken.has(withSuffix)) {
      return withSuffix
    }
  }

  return candidate
}
