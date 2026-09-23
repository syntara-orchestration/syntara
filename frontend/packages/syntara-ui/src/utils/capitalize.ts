/**
 * Uppercases the first character of a string and leaves the rest unchanged.
 * Use for display labels derived from API enum values (e.g. "pending" → "Pending").
 */
export function capitalize(value: string): string {
  if (value.length === 0) return value
  return value.charAt(0).toUpperCase() + value.slice(1)
}
