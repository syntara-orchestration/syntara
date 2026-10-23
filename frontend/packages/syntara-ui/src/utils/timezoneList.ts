let cachedTimezones: string[] | null = null

/** Resolve the current browser timezone, falling back to UTC when unavailable. */
export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

/** IANA timezone identifiers supported by the runtime (cached). */
export function getIanaTimezones(): string[] {
  if (!cachedTimezones) {
    let timezones: string[]
    try {
      timezones = Intl.supportedValuesOf('timeZone')
    } catch {
      timezones = ['UTC']
    }
    const browserTimezone = getBrowserTimezone()
    cachedTimezones = [browserTimezone, ...timezones.filter((timezone) => timezone !== browserTimezone)]
  }
  return cachedTimezones
}
