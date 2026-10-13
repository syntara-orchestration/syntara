let cachedTimezones: string[] | null = null

/** IANA timezone identifiers supported by the runtime (cached). */
export function getIanaTimezones(): string[] {
  if (!cachedTimezones) {
    try {
      cachedTimezones = Intl.supportedValuesOf('timeZone')
    } catch {
      cachedTimezones = ['UTC']
    }
  }
  return cachedTimezones
}
