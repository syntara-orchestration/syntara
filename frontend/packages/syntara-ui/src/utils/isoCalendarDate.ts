/**
 * Calendar-date validation for YYYY-MM-DD strings without relying on
 * `Date` parsing quirks (e.g. years 0–99 mapping to 1900–1999).
 */

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

/** Returns true when `value` is a real calendar date in YYYY-MM-DD form. */
export function isValidIsoCalendarDate(value: string): boolean {
  if (!ISO_DATE_PATTERN.test(value)) {
    return false
  }

  const year = Number(value.slice(0, 4))
  const month = Number(value.slice(5, 7))
  const day = Number(value.slice(8, 10))
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    return false
  }
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return false
  }

  // Parse with the full YYYY-MM-DD string so years 0001–0099 are not remapped like Date.UTC(0–99, …).
  const parsed = new Date(`${value}T00:00:00.000Z`)
  if (Number.isNaN(parsed.getTime())) {
    return false
  }
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day
}
