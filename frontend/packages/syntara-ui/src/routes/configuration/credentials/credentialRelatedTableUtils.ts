/** Em dash used when a related-resource table cell has no value. */
export const RELATED_RESOURCE_DASH = '\u2014'

export function hasTrimmedDescription(description: string | null | undefined): boolean {
  return Boolean(description?.trim())
}

export function relatedResourceRowId(id: string | null | undefined, fallbackPrefix: string, index: number): string {
  return id ?? `${fallbackPrefix}-${index}`
}

export function expandableRowIds<T extends { id?: string | null; description?: string | null }>(
  items: T[],
  fallbackPrefix: string
): string[] {
  return items.flatMap((item, index) =>
    hasTrimmedDescription(item.description) ? [relatedResourceRowId(item.id, fallbackPrefix, index)] : []
  )
}
