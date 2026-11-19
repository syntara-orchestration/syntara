/** Shown for every unsupported RFC 3339 date include combination (builder, canvas, and API copy). */
export const DATE_FIELD_RFC3339_COMBINATION_MESSAGE =
  'Choose date only, time with timezone, or date and time with timezone.'

/** Map backend API wording to the standard combination message for inline display. */
export function normalizeDateFieldCombinationMessage(raw: string): string | null {
  const trimmed = raw.trim()
  if (trimmed === DATE_FIELD_RFC3339_COMBINATION_MESSAGE) {
    return DATE_FIELD_RFC3339_COMBINATION_MESSAGE
  }
  if (/unsupported combination of date components/i.test(trimmed)) {
    return DATE_FIELD_RFC3339_COMBINATION_MESSAGE
  }
  return null
}
