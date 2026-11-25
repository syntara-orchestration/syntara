/**
 * Escapes regular-expression metacharacters so a string can be used as a literal in `RegExp`.
 */
export function escapeRegExp(value: string): string {
  return value.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Matches strings that start with `value`. Use when the accessible name includes extra text
 * after the label (e.g. PatternFly SelectOption descriptions).
 */
export function regExpPrefixMatch(value: string): RegExp {
  return new RegExp(`^${escapeRegExp(value)}`)
}
